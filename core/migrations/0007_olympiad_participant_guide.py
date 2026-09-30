from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("core", "0006_alter_olympiad_level")]

    operations = [
        migrations.AddField("olympiad", "participation_details", models.TextField("Условия и порядок участия", blank=True)),
        migrations.AddField("olympiad", "preparation", models.TextField("Темы и подготовка", blank=True)),
        migrations.AddField("olympiad", "assessment", models.TextField("Оценивание и результаты", blank=True)),
    ]
