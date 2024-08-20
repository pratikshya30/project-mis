from django.core.management.base import BaseCommand
from scrapper.models import Email

class Command(BaseCommand):
    help = 'Show all saved emails'

    def handle(self, *args, **kwargs):
        emails = Email.objects.all()
        if emails:
            self.stdout.write("Saved Emails:")
            for email in emails:
                self.stdout.write(email.email)
        else:
            self.stdout.write("No emails found.")
