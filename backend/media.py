import os
import pwd

from flask import Blueprint, abort, jsonify, request, send_file


media_api = Blueprint('media', __name__, url_prefix='/api/media')

MEDIA_EXTENSIONS = {'.aac', '.flac', '.m4a', '.mp3', '.ogg', '.opus', '.wav', '.webm'}
MEDIA_MOUNT_BASES = ('/media', '/run/media')


def _media_user():
    return pwd.getpwuid(os.geteuid())


def _is_mounted_volume(path):
    return os.path.ismount(path)


def _media_roots():
    user = _media_user()
    roots = []

    music = os.path.join(user.pw_dir, 'Music')
    if os.path.isdir(music):
        roots.append(os.path.realpath(music))

    for base in MEDIA_MOUNT_BASES:
        mount_parent = os.path.join(base, user.pw_name)
        try:
            with os.scandir(mount_parent) as entries:
                for entry in sorted(entries, key=lambda item: item.name.casefold()):
                    try:
                        if entry.name.startswith('.') or not entry.is_dir(follow_symlinks=False):
                            continue
                        if not _is_mounted_volume(entry.path):
                            continue
                        path = os.path.realpath(entry.path)
                        if path not in roots:
                            roots.append(path)
                    except OSError:
                        # A volume can disappear while roots are being listed.
                        continue
        except OSError:
            # The mount parent may not exist until the first USB is mounted.
            continue
    return roots


def _is_within_root(path, root):
    try:
        return os.path.commonpath((path, root)) == root
    except ValueError:
        return False


def _safe_media_path(value):
    path = os.path.realpath(value or '')
    if not any(_is_within_root(path, root) for root in _media_roots()):
        abort(403)
    return path


@media_api.get('/roots')
def media_roots():
    return jsonify([
        {'name': os.path.basename(path) or path, 'path': path}
        for path in _media_roots()
    ])


@media_api.get('/browse')
def media_browse():
    path = _safe_media_path(request.args.get('path'))
    if not os.path.isdir(path):
        abort(404)

    entries = []
    try:
        with os.scandir(path) as iterator:
            for entry in iterator:
                if entry.name.startswith('.'):
                    continue
                if entry.is_dir(follow_symlinks=False):
                    entries.append({'kind': 'directory', 'name': entry.name, 'path': entry.path})
                elif (
                    entry.is_file(follow_symlinks=False)
                    and os.path.splitext(entry.name)[1].lower() in MEDIA_EXTENSIONS
                ):
                    entries.append({'kind': 'file', 'name': entry.name, 'path': entry.path})
    except OSError:
        abort(403)

    entries.sort(key=lambda item: (item['kind'] != 'directory', item['name'].lower()))
    return jsonify({
        'name': os.path.basename(path) or path,
        'path': path,
        'entries': entries,
    })


@media_api.get('/file')
def media_file():
    path = _safe_media_path(request.args.get('path'))
    if not os.path.isfile(path) or os.path.splitext(path)[1].lower() not in MEDIA_EXTENSIONS:
        abort(404)
    return send_file(path, conditional=True)
