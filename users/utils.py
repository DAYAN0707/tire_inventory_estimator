import logging # ロギングモジュールをインポートして、デモユーザーの操作を記録するためのロガーを設定
from django.core.exceptions import PermissionDenied # 権限エラーを送出するための例外クラスをインポート
from django.contrib import messages # ユーザーにフィードバックを表示するためのモジュール（成功・エラーなどのメッセージ）
from django.shortcuts import redirect # 画面表示、オブジェクト取得、リダイレクトのためのショートカット関数

# デモユーザーの操作を制限するユーティリティ関数
logger = logging.getLogger(__name__)

def stop_demo_user(view_func):
    # デモユーザーの操作を制限するデコレータ
    def _wrapped_view(request, *args, **kwargs):
        # デモユーザーかどうかをチェック
        if request.user.is_authenticated and request.user.groups.filter(name="demo_group").exists():
            # ログに記録（最強の抑止力）
            messages.warning(request, "デモアカウントではユーザー情報の編集・削除は制限されています。")
            
            # 🌟 元のページに戻す
            return redirect(request.META.get('HTTP_REFERER', 'users:user_list'))
        # デモユーザーでなければ通常通り処理を続行
        return view_func(request, *args, **kwargs)
    # デコレータのメタデータを保持
    return _wrapped_view