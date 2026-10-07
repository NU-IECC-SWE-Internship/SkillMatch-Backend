from django.db import migrations, models
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ('skillmatch', '0013_skill_approval_quiz_abandoned'),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name='skillquizquestion',
            name='unique_skill_quiz_order',
        ),
        migrations.RemoveField(
            model_name='skillquizquestion',
            name='order',
        ),
        migrations.AddField(
            model_name='skillquizquestion',
            name='cycle',
            field=models.CharField(db_index=True, default='', max_length=7),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='skillquizquestion',
            name='created_at',
            field=models.DateTimeField(auto_now_add=True, default=django.utils.timezone.now),
            preserve_default=False,
        ),
        migrations.AlterModelOptions(
            name='skillquizquestion',
            options={'ordering': ['skill', '-cycle', 'id']},
        ),
    ]
