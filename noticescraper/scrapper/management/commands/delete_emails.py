from django.core.management.base import BaseCommand
from scrapper.models import Email

class Command(BaseCommand):
    help = 'Deletes all email records from the database'

    def handle(self, *args, **kwargs):
        deleted_count, _ = Email.objects.all().delete()
        self.stdout.write(self.style.SUCCESS(f'Successfully deleted {deleted_count} email(s).'))
