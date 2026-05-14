from django.core.management.base import BaseCommand # Djangoのカスタム管理コマンドを作成するためのベースクラスをインポート
from django.contrib.auth.models import Group # グループモデルをインポートして、デモグループの作成に使用
from django.contrib.auth import get_user_model # カスタムユーザーモデルを取得

User = get_user_model()

# デモユーザーとグループを完全再現する管理コマンド
class Command(BaseCommand):
    help = "スクリーンショットの設定に基づきデモユーザーとグループを完全再現します"

    def handle(self, *args, **options):
        # 1. グループの作成 (image_d8219c.jpg)
        demo_group, _ = Group.objects.get_or_create(name="demo_group")

        # 2. デモ店長の作成 (image_d82124.jpg / image_d81e3d.jpg)
        manager, created = User.objects.get_or_create(
            username="demo_manager",
            defaults={
                "employee_id": "111111",
                "employee_name": "デモ店長",
                "is_staff": True,      # 管理者権限
                "is_active": True,     # 有効フラグ
                "is_superuser": False, # スーパーユーザーではない
            }
        )
        if created:
            manager.set_password("demo1234")
            manager.save()
            self.stdout.write(self.style.SUCCESS("Created: demo_manager (111111)"))
        
        # グループに所属させる
        manager.groups.add(demo_group)

        # 3. デモスタッフの作成 (image_d81da6.jpg / image_d81a7c.jpg)
        staff, created = User.objects.get_or_create(
            username="demo_staff",
            defaults={
                "employee_id": "222222",
                "employee_name": "デモスタッフ",
                "is_staff": False,     # 管理者権限なし
                "is_active": True,     # 有効フラグ（スタッフ判別用）
                "is_superuser": False,
            }
        )
        if created:
            staff.set_password("demo1234")
            staff.save()
            self.stdout.write(self.style.SUCCESS("Created: demo_staff (222222)"))
            
        # グループに所属させる
        staff.groups.add(demo_group)

        self.stdout.write(self.style.SUCCESS("--- 管理画面の設定どおりに復元完了しました ---"))