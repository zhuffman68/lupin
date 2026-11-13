"""Account for hard-linked, app-owned installer cache files without following links."""
from pathlib import Path
import re
import stat


def managed(name):
    return bool(re.fullmatch(r'base-[0-9a-f]{64}',name) or
                name.startswith(('Lupin-','lupin-')) and name.endswith(('.exe','.deb','.pkg.tar.zst','.zip','.lupinpatch','.part')))


def files(folder):
    try:paths=list(Path(folder).iterdir())
    except OSError:return []
    result=[]
    for path in paths:
        try:info=path.lstat()
        except OSError:continue
        if managed(path.name) and stat.S_ISREG(info.st_mode):result.append((path,info))
    return result


def usage(folder):
    seen=set();total=0
    for _,info in files(folder):
        identity=(info.st_dev,info.st_ino)
        if identity not in seen:seen.add(identity);total+=info.st_size
    return total


def clear(folder):
    for path,_ in files(folder):path.unlink(missing_ok=True)
