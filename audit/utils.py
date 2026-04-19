import logging
from .models import AuditLog

# ロガーのセットアップ （このモジュール専用のロガーを作ることで、監査ログ関連のエラーを特定しやすくする）
logger = logging.getLogger(__name__)

def get_client_ip(request):
    """リクエストからIPアドレスを取得する"""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip

def write_audit_log(
    *,
    request=None,  # Noneを許容することで、バッチ処理等でも使いやすく改善
    target_type,
    target_id,
    action,
    before=None,
    after=None,
    note=""
):
    """監査ログを安全に記録するためのユーティリティ関数
    - request: ログを記録する際のユーザー情報やIPアドレスを取得するために使用（任意）"""
    try:
        actor = None
        ip = None

        # リクエストがある場合のみ、ユーザー情報とIPを取得
        if request:
            actor = request.user if request.user.is_authenticated else None
            ip = get_client_ip(request)

        # 監査ログの作成（DBへの保存はここで一度だけ！）
        AuditLog.objects.create(
            target_type=target_type,
            target_id=target_id,
            action=action,
            actor=actor,
            before_value=before,
            after_value=after,
            ip_address=ip,
            note=note
        )

    except Exception:
        # printではなくloggerを使うことで、本番環境のログファイルに出力可能にする
        logger.exception("監査ログの記録に失敗しました")