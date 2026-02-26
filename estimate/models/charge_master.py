from django.db import models

class ChargeMaster(models.Model):
    name = models.CharField(max_length=100)
    unit_price = models.IntegerField()
    is_active = models.BooleanField(default=True)


    class ChargeType(models.TextChoices):
        INSTALL = "install", "交換工賃"
        WASTE = "waste", "廃タイヤ"
        VALVE = "valve", "バルブ"
        RFT = "rft", "RFT加算"

    name = models.CharField(max_length=100)
    charge_type = models.CharField(
        max_length=20,
        choices=ChargeType.choices
    )
    unit_price = models.IntegerField()
    is_active = models.BooleanField(default=True)