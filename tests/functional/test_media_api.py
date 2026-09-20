import os
from types import SimpleNamespace

import pytest
from flask import Flask

from backend import media
from backend.media import media_api


@pytest.fixture()
def media_layout(tmp_path, monkeypatch):
    home = tmp_path / 'home' / 'testuser'
    home.mkdir(parents=True)
    music = home / 'Music'
    music.mkdir()
    media_parent = tmp_path / 'media' / 'testuser'
    run_media_parent = tmp_path / 'run' / 'media' / 'testuser'
    media_parent.mkdir(parents=True)
    run_media_parent.mkdir(parents=True)
    mounted = set()

    monkeypatch.setattr(media, '_media_user', lambda: SimpleNamespace(pw_name='testuser', pw_dir=str(home)))
    monkeypatch.setattr(media, 'MEDIA_MOUNT_BASES', (str(media_parent.parent), str(run_media_parent.parent)))
    monkeypatch.setattr(media, '_is_mounted_volume', lambda path: path in mounted)

    def add_usb(name, parent=media_parent):
        volume = parent / name
        volume.mkdir()
        mounted.add(str(volume))
        return volume

    return SimpleNamespace(
        music=music,
        media_parent=media_parent,
        run_media_parent=run_media_parent,
        mounted=mounted,
        add_usb=add_usb,
    )


@pytest.fixture()
def media_root(media_layout):
    return media_layout.music


@pytest.fixture()
def media_client(media_layout):
    app = Flask(__name__)
    app.config.update(TESTING=True)
    app.register_blueprint(media_api)
    return app.test_client()


def test_server_registers_media_blueprint():
    from backend.server import server

    rules = {rule.rule for rule in server.url_map.iter_rules()}

    assert 'media' in server.blueprints
    assert {
        '/api/media/roots',
        '/api/media/browse',
        '/api/media/file',
    } <= rules


def test_roots_include_music_without_linux_parent_directories(media_client, media_layout):
    response = media_client.get('/api/media/roots')

    assert response.status_code == 200
    assert response.get_json() == [{'name': 'Music', 'path': str(media_layout.music)}]
    assert all(root['name'] not in {'media', 'mnt', 'testuser'} for root in response.get_json())


def test_roots_show_each_mounted_usb_directly(media_client, media_layout):
    pablo = media_layout.add_usb('Pablo')
    sandisk = media_layout.add_usb('SANDISK')
    run_usb = media_layout.add_usb('USB64GB', media_layout.run_media_parent)
    (media_layout.media_parent / 'not-mounted').mkdir()
    media_layout.add_usb('.hidden')

    response = media_client.get('/api/media/roots')

    assert response.status_code == 200
    assert response.get_json() == [
        {'name': 'Music', 'path': str(media_layout.music)},
        {'name': 'Pablo', 'path': str(pablo)},
        {'name': 'SANDISK', 'path': str(sandisk)},
        {'name': 'USB64GB', 'path': str(run_usb)},
    ]


def test_roots_skip_missing_music_and_duplicate_real_paths(media_client, media_layout):
    media_layout.music.rmdir()
    usb = media_layout.add_usb('Pablo')
    media_layout.music.symlink_to(usb, target_is_directory=True)

    roots = media_client.get('/api/media/roots').get_json()

    assert roots == [{'name': 'Pablo', 'path': str(usb)}]

    media_layout.music.unlink()
    assert media_client.get('/api/media/roots').get_json() == [
        {'name': 'Pablo', 'path': str(usb)},
    ]


def test_unmounted_usb_disappears_and_cannot_be_browsed(media_client, media_layout):
    usb = media_layout.add_usb('Pablo')
    assert {'name': 'Pablo', 'path': str(usb)} in media_client.get('/api/media/roots').get_json()

    media_layout.mounted.remove(str(usb))

    assert {'name': 'Pablo', 'path': str(usb)} not in media_client.get('/api/media/roots').get_json()
    assert media_client.get('/api/media/browse', query_string={'path': str(usb)}).status_code == 403


def test_browse_returns_directories_then_supported_audio_files(media_client, media_root):
    (media_root / 'zebra').mkdir()
    (media_root / 'Albums').mkdir()
    (media_root / 'Beta.FLAC').write_bytes(b'flac')
    (media_root / 'alpha.mp3').write_bytes(b'mp3')
    (media_root / 'notes.txt').write_text('not audio')
    (media_root / '.hidden.ogg').write_bytes(b'hidden')

    response = media_client.get('/api/media/browse', query_string={'path': str(media_root)})

    assert response.status_code == 200
    payload = response.get_json()
    assert payload['name'] == 'Music'
    assert payload['path'] == str(media_root)
    assert [(entry['kind'], entry['name']) for entry in payload['entries']] == [
        ('directory', 'Albums'),
        ('directory', 'zebra'),
        ('file', 'alpha.mp3'),
        ('file', 'Beta.FLAC'),
    ]


def test_usb_browse_and_file_streaming(media_client, media_layout):
    usb = media_layout.add_usb('Pablo')
    album = usb / 'Album'
    album.mkdir()
    track = album / 'song.mp3'
    track.write_bytes(b'0123456789')

    root_browse = media_client.get('/api/media/browse', query_string={'path': str(usb)})
    album_browse = media_client.get('/api/media/browse', query_string={'path': str(album)})
    streamed = media_client.get(
        '/api/media/file',
        query_string={'path': str(track)},
        headers={'Range': 'bytes=2-5'},
    )

    assert root_browse.status_code == 200
    assert root_browse.get_json()['entries'] == [
        {'kind': 'directory', 'name': 'Album', 'path': str(album)},
    ]
    assert album_browse.get_json()['entries'] == [
        {'kind': 'file', 'name': 'song.mp3', 'path': str(track)},
    ]
    assert streamed.status_code == 206
    assert streamed.data == b'2345'


def test_browse_rejects_paths_outside_discovered_roots(media_client, media_root):
    outside = media_root.parent / 'Music-backup'
    outside.mkdir()

    response = media_client.get('/api/media/browse', query_string={'path': str(outside)})

    assert response.status_code == 403


def test_usb_rejects_parent_traversal_and_symlink_escape(media_client, media_layout):
    usb = media_layout.add_usb('Pablo')
    outside = media_layout.media_parent / 'private.mp3'
    outside.write_bytes(b'private')
    (usb / 'linked.mp3').symlink_to(outside)

    assert media_client.get(
        '/api/media/browse', query_string={'path': str(usb / '..')},
    ).status_code == 403
    assert media_client.get(
        '/api/media/file', query_string={'path': str(usb / 'linked.mp3')},
    ).status_code == 403
    assert media_client.get(
        '/api/media/file', query_string={'path': str(outside)},
    ).status_code == 403


def test_usb_rejects_unsupported_extension(media_client, media_layout):
    usb = media_layout.add_usb('Pablo')
    unsupported = usb / 'notes.txt'
    unsupported.write_text('not audio')

    assert media_client.get(
        '/api/media/file', query_string={'path': str(unsupported)},
    ).status_code == 404


def test_browse_returns_not_found_for_missing_path_inside_root(media_client, media_root):
    response = media_client.get(
        '/api/media/browse',
        query_string={'path': str(media_root / 'missing')},
    )

    assert response.status_code == 404


def test_browse_maps_filesystem_errors_to_forbidden(media_client, media_root, monkeypatch):
    def denied_scandir(_path):
        raise PermissionError

    monkeypatch.setattr(os, 'scandir', denied_scandir)

    response = media_client.get('/api/media/browse', query_string={'path': str(media_root)})

    assert response.status_code == 403


def test_symlinks_cannot_escape_media_root(media_client, media_root):
    outside = media_root.parent / 'private.mp3'
    outside.write_bytes(b'private')
    link = media_root / 'linked.mp3'
    link.symlink_to(outside)

    browse_response = media_client.get(
        '/api/media/browse',
        query_string={'path': str(media_root)},
    )
    file_response = media_client.get(
        '/api/media/file',
        query_string={'path': str(link)},
    )

    assert all(entry['name'] != link.name for entry in browse_response.get_json()['entries'])
    assert file_response.status_code == 403


def test_file_serves_audio_and_supports_range_requests(media_client, media_root):
    track = media_root / 'track.mp3'
    track.write_bytes(b'0123456789')

    response = media_client.get('/api/media/file', query_string={'path': str(track)})
    range_response = media_client.get(
        '/api/media/file',
        query_string={'path': str(track)},
        headers={'Range': 'bytes=2-5'},
    )

    assert response.status_code == 200
    assert response.data == b'0123456789'
    assert response.mimetype == 'audio/mpeg'
    assert range_response.status_code == 206
    assert range_response.data == b'2345'
    assert range_response.headers['Content-Range'] == 'bytes 2-5/10'


def test_file_rejects_unsupported_extensions(media_client, media_root):
    unsupported = media_root / 'notes.txt'
    unsupported.write_text('not audio')

    response = media_client.get('/api/media/file', query_string={'path': str(unsupported)})

    assert response.status_code == 404
