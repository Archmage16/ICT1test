from django import template
from core.ui_text import translate

register = template.Library()
register.simple_tag(translate, name="tr")
register.filter("tr", translate)
