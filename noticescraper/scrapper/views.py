from django.shortcuts import render, redirect
from .forms import EmailForm
import logging
import pymongo
from bson import ObjectId  # Import ObjectId from bson
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os
from dotenv import load_dotenv
import requests
from email.mime.base import MIMEBase
from email import encoders

# Load environment variables from .env file
load_dotenv()

# Configure logging
logger = logging.getLogger(__name__)

# Connect to MongoDB
client = pymongo.MongoClient(os.getenv('MONGO_URI'))
db = client['mis']
email_collection = db['emails']  # Use 'emails' collection in MongoDB
notice_collection = db['notices']

def home(request):
    form = EmailForm()
    if request.method == 'POST':
        form = EmailForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data['email']
            existing_email = email_collection.find_one({'email': email})
            if existing_email:
                messages = ["Email already exists."]
            else:
                email_collection.insert_one({'email': email})
                messages = ["Email added successfully."]
            return render(request, 'home.html', {'form': form, 'messages': messages, 'emails': get_emails()})

    return render(request, 'home.html', {'form': form, 'emails': get_emails()})

def edit_email(request, email_id):
    email = email_collection.find_one({'_id': ObjectId(email_id)})
    if not email:
        return redirect('home')

    if request.method == 'POST':
        new_email = request.POST.get('email')
        if new_email:
            email_collection.update_one({'_id': ObjectId(email_id)}, {'$set': {'email': new_email}})
            return redirect('home')

    return render(request, 'edit_email.html', {'email': email})

def delete_email(request, email_id):
    email_collection.delete_one({'_id': ObjectId(email_id)})
    return redirect('home')

def get_emails():
    emails = email_collection.find()
    return [{'email': email.get('email'), 'id': str(email.get('_id'))} for email in emails]

def format_subject(title):
    # Split the title by hyphens, capitalize each word, and join with spaces
    words = title.split('-')
    formatted_title = ' '.join(word.capitalize() for word in words)
    return formatted_title

def send_email(subject, body, recipients, image_links):
    sender_email = os.getenv('EMAIL')
    sender_password = os.getenv('EMAIL_PASSWORD')

    # Format the subject to capitalize words and separate by spaces
    formatted_subject = format_subject(subject)

    for recipient in recipients:
        msg = MIMEMultipart()
        msg['From'] = sender_email
        msg['To'] = recipient
        msg['Subject'] = formatted_subject

        msg.attach(MIMEText(body, 'plain'))

        # Download and attach each image
        for i, img_link in enumerate(image_links):
            try:
                response = requests.get(img_link)
                response.raise_for_status()  # Check if the download was successful

                img_data = response.content
                img_name = f"image_{i + 1}.jpg"

                # Create a MIMEBase object to attach the image
                img_part = MIMEBase('application', 'octet-stream')
                img_part.set_payload(img_data)
                encoders.encode_base64(img_part)
                img_part.add_header('Content-Disposition', f'attachment; filename={img_name}')

                # Attach the image to the email
                msg.attach(img_part)
            except Exception as e:
                logger.error(f"Failed to download or attach image from {img_link}: {e}")

        try:
            server = smtplib.SMTP('smtp.gmail.com', 587)
            server.set_debuglevel(1)
            server.starttls()
            server.login(sender_email, sender_password)
            text = msg.as_string()
            server.sendmail(sender_email, recipient, text)
            server.quit()
            logger.debug(f"Email sent to: {recipient}")
        except Exception as e:
            logger.error(f"Failed to send email to {recipient}: {e}")

def scrape_images(request):
    try:
        logger.info("Starting the scraping process...")
        
        url = "https://sxc.edu.np/notice"
        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_driver_path = os.getenv('DRIVER_LOCATION')
        service = Service(chrome_driver_path)

        logger.debug("Starting the Chrome WebDriver...")
        driver = webdriver.Chrome(service=service, options=chrome_options)
        driver.get(url)

        logger.debug("Waiting for notices to load...")
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, '.fixed-image.cover.fixed-image-holder'))
        )

        divs = driver.find_elements(By.CSS_SELECTOR, '.fixed-image.cover.fixed-image-holder')
        new_notice_found = False
        image_links = []

        for div in divs:
            img_tag = div.find_element(By.TAG_NAME, 'img')
            img_link = img_tag.get_attribute('src')
            img_key = img_link.split('/')[-1]
            notice_title = div.find_element(By.XPATH, '..').get_attribute('href').split('/')[-1]

            # Check if the notice already exists in the database
            existing_notice = notice_collection.find_one({"_id": notice_title})
            if existing_notice:
                # Update the notice if it exists
                logger.debug(f"Notice already exists: {notice_title}. Updating the database...")
                notice_collection.update_one(
                    {"_id": notice_title},
                    {"$set": {
                        "filename": img_key,
                        "img_link": img_link
                    }}
                )
            else:
                # Insert the new notice if it doesn't exist
                logger.debug(f"New notice found: {notice_title}. Saving to database...")
                notice_collection.insert_one({
                    "_id": notice_title,
                    "filename": img_key,
                    "img_link": img_link
                })
                new_notice_found = True
                subject = f"New Notice: {notice_title}"
                body = f"We found a new notice. View the notice to stay updated with the latest information."
                image_links.append(img_link)  # Collect image links

        driver.quit()

        if new_notice_found:
            logger.info("Scraping completed successfully.")
            # Fetch all emails from MongoDB
            email_docs = email_collection.find()
            emails = [email_doc['email'] for email_doc in email_docs]
            if emails:
                send_email(subject, body, emails, image_links)
                messages = [f"Notice: {notice_title}, Email sent to: {', '.join(emails)}"]
            else:
                messages = [f"Notice: {notice_title}, but no emails found in the database."]
            return render(request, 'success.html', {'messages': messages, 'images': image_links})
        else:
            logger.info("No new notices found.")
            return render(request, 'no_new_notice.html')

    except Exception as e:
        logger.error(f"Error during scraping: {e}", exc_info=True)
        return render(request, 'error.html')

def view_notices(request):
    try:
        # Fetch all notices from the MongoDB collection
        notices = notice_collection.find()
        
        # Convert MongoDB cursor to a list of dictionaries
        notice_list = [{
            "title": format_subject(notice.get("_id")),
            "filename": notice.get("filename"),
            "img_link": notice.get("img_link")
        } for notice in notices]
        
        return render(request, 'view_notices.html', {'notices': notice_list})
    
    except Exception as e:
        logger.error(f"Error retrieving notices: {e}", exc_info=True)
        return render(request, 'error.html')
