from easyocr import Reader
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import cv2
import pandas as pd
import smtplib
import os
from twilio.rest import Client
import geocoder
import re
import argparse
import time

def get_args():
    parser = argparse.ArgumentParser(description='Smart Traffic Monitor')
    parser.add_argument('--test', action='store_true', 
                        help='Use test license plates instead of OCR')
    parser.add_argument('--plate', type=str, default="TN57CB4422",
                        help='Test license plate to use if --test is enabled')
    parser.add_argument('--debug', action='store_true',
                        help='Print debug information')
    return parser.parse_args()

def debug_print(message, args):
    if args.debug:
        print(f"DEBUG: {message}")

print("Starting Smart Traffic Monitor...")

# Try to get location, but handle errors gracefully
try:
    g = geocoder.ip('me')
    if g and hasattr(g, 'address') and g.address:
        print(f"Got location: {g.address}")
        if hasattr(g, 'json') and g.json and 'address' in g.json:
            CAMERA_LOCATION = g.json['address']+f'. [Lat: {g.lat}, Lng:{g.lng}]'
        else:
            CAMERA_LOCATION = f"Location: {g.address}"
    else:
        print("Could not determine location details")
        CAMERA_LOCATION = "Unknown location"
except Exception as e:
    print(f"Error getting location: {e}")
    CAMERA_LOCATION = "Unknown location"

print(f"Camera location set to: {CAMERA_LOCATION}")

def sendSMS(number):
    print(f"Sending SMS to {number}")
    try:
        TWILIO_ACCOUNT_SID = 'ACdf6412364abcb03f35ce92810386dbc4'
        TWILIO_AUTH_TOKEN = '7d31334ccca88ea2329b5b7b0d9f64f5'

        client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

        message = client.messages \
            .create(
                body=f'You were caught riding without helmet near {CAMERA_LOCATION}, and were fined Rupees 500. Please visit https://echallan.parivahan.gov.in/ to pay your due challan. If you are caught riding again without proper gear, you will be severely penalized.',
                from_='+19203455833',
                to=f'+{number}'
            )

        print(message.sid)
        return True
    except Exception as e:
        print(f"SMS sending error: {e}")
        return False

def sendMail(mail):
    print(f"Sending email to {mail}")
    try:
        message = MIMEMultipart("alternative")
        message["Subject"] = 'Notification regarding e-challan fine'
        message["From"] = mail
        message["To"] = mail
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.ehlo()
        server.starttls()
        server.ehlo()

        body = f'You were caught riding without helmet near {CAMERA_LOCATION}, and were fined Rupees 500. Please visit https://echallan.parivahan.gov.in/ to pay your due challan. If you are caught riding again without proper gear, you will be severely penalized.'

        message.attach(MIMEText(body, "plain"))
        server.login('smart.traffic.monitor@gmail.com', 'vimtcznlsxshqyrp')
        server.sendmail('smart.traffic.monitor@gmail.com', mail, message.as_string())
        server.quit()
        print(f"Email sent to {mail}")
        return True
    except Exception as e:
        print(f"Email sending error: {e}")
        return False
  
# Load database
database = pd.read_csv('database.csv')
print(f"Loaded database with {len(database)} records")

BASE_DIR = 'yolo/runs/detect/exp/crops/No-helmet'
print(f"Looking for images in {BASE_DIR}")

def process_license_plate(licensePlate, warnedNums, args):
    print(f"Processing license plate: {licensePlate}")
    
    if licensePlate not in warnedNums:
        found = False
        for index, plate in enumerate(database['Registration']):
            debug_print(f"Comparing {licensePlate} with {plate}", args)
            if licensePlate == plate:
                found = True
                print(f"Match found! {database['Name'][index]}")
                
                # Update the due challan
                database.at[index, 'Due challan'] += 500
                mail = database['Email'][index]
                num = database['Phone number'][index]
                
                # Send notifications
                email_sent = sendMail(mail)
                sms_sent = sendSMS(num)
                
                if email_sent or sms_sent:
                    print(f"{database['Name'][index]} notified!")
                    warnedNums.append(licensePlate)
                    database.to_csv('database.csv', index=False)
                else:
                    print(f"Failed to notify {database['Name'][index]}")
                break
        
        if not found:
            print(f"No match found for license plate: {licensePlate}")
            debug_print("All plates in database:", args)
            for i, p in enumerate(database['Registration']):
                debug_print(f"  {i+1}. {p}", args)
    
    return warnedNums


if __name__ == '__main__':
    args = get_args()
    print("Starting main processing loop")
    warnedNums = []

    if args.debug:
        print("\nAvailable registration numbers in database:")
        for i, plate in enumerate(database['Registration']):
            print(f"  {i+1}. {plate}")

    if args.test:
        print(f"TEST MODE: Using test license plate: {args.plate}")
        warnedNums = process_license_plate(args.plate, warnedNums, args)
    else:
        if not os.path.exists(BASE_DIR):
            print(f"Error: Directory {BASE_DIR} does not exist")
            exit(1)
            
        image_files = os.listdir(BASE_DIR)
        print(f"Found {len(image_files)} images to process")
        
        for path in image_files:
            numberplate_path = os.path.join(BASE_DIR, path).replace('No-helmet', 'Numberplate')
            print(f"Processing image: {path}")
            print(f"Looking for numberplate at: {numberplate_path}")
            
            try:
                img = cv2.imread(numberplate_path, 0)
                if img is None:
                    print(f"Failed to read image: {numberplate_path}")
                    continue
                    
                print("Initializing OCR reader...")
                reader = Reader(['en'])
                
                print("Starting OCR detection (this may take time)...")
                start_time = time.time()
                number = reader.readtext(img, mag_ratio=3)
                end_time = time.time()
                print(f"OCR completed in {end_time - start_time:.2f} seconds")
                
                print(f"OCR detected: {number}")
                
                licensePlate = ""

                try:
                    for i in [0, 1]:
                        for item in number[i]:
                            if type(item) == str:
                                licensePlate += item
                except IndexError:
                    print(f"Not enough text detected in the image")
                    continue

                licensePlate = licensePlate.replace(' ', '')
                licensePlate = licensePlate.upper()
                licensePlate = re.sub(r'[^a-zA-Z0-9]', '', licensePlate)
                print('License number is:', licensePlate)

                warnedNums = process_license_plate(licensePlate, warnedNums, args)
                
            except Exception as e:
                print(f"Error processing {path}: {str(e)}")
    
    print("Processing complete!")