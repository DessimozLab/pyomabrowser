from celery import shared_task
from django.core.mail import EmailMessage
from django.conf import settings
import logging
logger = logging.getLogger(__name__)


@shared_task
def subscribe_to_mailing_list(email, name=None):
    body = "join address={} {}".format(email, "" if name is None else name)
    sender = settings.MAILMAN_SUBSCRIBE['sender']
    mailinglist = settings.MAILMAN_SUBSCRIBE['mailinglist']
    msg = EmailMessage(body=body, from_email=sender, to=[mailinglist])
    msg.send()
    logger.info('registration email for {} sent to {}'.format(email, mailinglist))
