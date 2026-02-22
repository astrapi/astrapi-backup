def ui_tag(tag_name):
    def decorator(func):
        setattr(func, "_ui_tag", tag_name)
        return func
    return decorator
