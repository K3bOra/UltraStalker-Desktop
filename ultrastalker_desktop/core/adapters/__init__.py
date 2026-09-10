from .stalker import StalkerAdapter
from .xtream import XtreamAdapter
from .m3u import M3UAdapter
from .cached import CachedAdapter
from ultrastalker_desktop.core.models import profile_identity

def make_adapter(profile):
    t=profile.source_type.lower()
    if t=='stalker': inner=StalkerAdapter(profile.portal_url,profile.mac)
    elif t=='xtream': inner=XtreamAdapter(profile.portal_url,profile.username,profile.password)
    elif t=='m3u': inner=M3UAdapter(profile.m3u_url or profile.portal_url)
    else: raise ValueError('Unsupported source type: '+t)
    return CachedAdapter(inner,profile_identity(profile))
