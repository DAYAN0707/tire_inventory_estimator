import csv
from django.core.management.base import BaseCommand
from inventory.models import Tire

# CSVファイルからタイヤデータをインポートするDjango管理コマンド
class Command(BaseCommand):
    help = 'CSVファイルからタイヤデータをインポートします'

    # コマンドライン引数としてCSVファイルのパスを受け取る
    def add_arguments(self, parser):
        parser.add_argument('csv_file', type=str)

    # CSVファイルを読み込んでデータベースに保存するロジック
    def handle(self, *args, **options):
        path = options['csv_file']
        # CSVファイルをUTF-8で読み込み、各行を辞書形式で処理
        with open(path, encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            # データベースに保存（既存のレコードはproduct_codeで更新、なければ新規作成）
            for row in reader:
                Tire.objects.update_or_create(
                    product_code=row['product_code'],
                    defaults={
                        'manufacturer': row['manufacturer'],
                        'brand': row['brand'], #
                        'size_raw': row['size_raw'],
                        'unit_price': int(row['unit_price']),
                        'set_price': int(row['set_price']) if row['set_price'] else None,
                        'stock_qty': int(row['stock_qty']),
                        'reorder_point': int(row['reorder_point']),
                    }
                )
        self.stdout.write(self.style.SUCCESS('インポート完了しました！'))