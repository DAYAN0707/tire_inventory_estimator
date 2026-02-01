import csv
from django.core.management.base import BaseCommand
from inventory.models import Tire, Inventory

class Command(BaseCommand):
    help = 'CSVからタイヤ＆在庫データをインポート'

    def handle(self, *args, **options):
        csv_path = 'csv/tires.csv'

        with open(csv_path, newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)

            for row in reader:
                tire, created = Tire.objects.get_or_create(
                    product_code=row['product_code'],
                    defaults={
                        'manufacturer': row['manufacturer'],
                        'brand': row['brand'],
                        'size_raw': row['size_raw'],
                        'unit_price': row['unit_price'],
                        'set_price': row['set_price'],
                        'load_index': row.get('load_index', ''),
                        'speed_symbol': row.get('speed_symbol', ''),
                    }
                )

                Inventory.objects.get_or_create(
                    tire=tire,
                    defaults={
                        'total_quantity': row['stock_qty'],
                        'reserved_quantity': 0,
                    }
                )

        self.stdout.write(self.style.SUCCESS('CSVインポート完了！'))


