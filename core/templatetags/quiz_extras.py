from django import template
register = template.Library()

@register.filter
def get_item(dictionary, key):
    """Get item from dictionary by key."""
    try:
        return dictionary[key]
    except Exception:
        try:
            return dictionary[str(key)]
        except Exception:
            return None