import logging
from celery import shared_task
from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils.html import strip_tags

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_rendered_email_task(self, subject: str, template_name: str, context: dict, recipient_list: list):
    if not recipient_list:
        return

    try:
        context.setdefault("site_url", getattr(settings, "FRONTEND_URL", "https://localhost:5173"))
        html_content = render_to_string(template_name, context)
        text_content = strip_tags(html_content)

        send_mail(
            subject=subject,
            message=text_content,
            html_message=html_content,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=recipient_list,
            fail_silently=False,
        )
        logger.info("Celery: Email '%s' successfully dispatched to %s", subject, recipient_list)
    except Exception as exc:
        logger.error("Celery: Failed to send email '%s' to %s: %s", subject, recipient_list, exc)
        raise self.retry(exc=exc)
