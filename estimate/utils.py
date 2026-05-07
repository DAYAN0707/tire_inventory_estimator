
def is_manager(user):
    """
    店長（is_staff）または管理者権限を持っているか判定
    """
    return user.is_authenticated and user.is_staff

def is_demo_staff_only(user):
    """
    デモグループに所属しているが、店長権限（is_staff）を持たない「一般デモスタッフ」か判定
    """
    return (
        user.is_authenticated 
        and user.groups.filter(name="demo_group").exists() 
        and not user.is_staff
    )