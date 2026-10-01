import os
import stat
import secrets
from pathlib import Path
OUTPUT_PREVIEW_BYTES = 16000

def _error_text(exc):
    return type(exc).__name__

def _artifact_directory():
    """Open the active profile's private output directory without symlinks."""
    from hermes_constants import get_hermes_home
    home = Path(get_hermes_home())
    if not home.is_absolute() or '..' in home.parts:
        raise ValueError('Hermes home must be an absolute path without dot segments.')
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    fd = os.open(home.anchor, flags)
    try:
        for part in home.parts[1:]:
            child = os.open(part, flags, dir_fd=fd)
            os.close(fd)
            fd = child
        try:
            os.mkdir('fulcra-output', mode=448, dir_fd=fd)
        except FileExistsError:
            pass
        child = os.open('fulcra-output', flags, dir_fd=fd)
        os.close(fd)
        fd = child
        info = os.fstat(fd)
        if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 448:
            raise PermissionError('fulcra-output must be owned by the current user with mode 0700.')
        return (home / 'fulcra-output', fd)
    except Exception:
        os.close(fd)
        raise

def _save_output(data):
    """Exclusively store complete UTF-8 bytes through a pinned directory FD."""
    directory, directory_fd = _artifact_directory()
    filename = None
    try:
        for _ in range(100):
            candidate = f'result-{secrets.token_hex(16)}.txt'
            try:
                fd = os.open(candidate, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 384, dir_fd=directory_fd)
            except FileExistsError:
                continue
            filename = candidate
            break
        else:
            raise FileExistsError('Could not allocate a unique output artifact.')
        with os.fdopen(fd, 'wb') as stream:
            os.fchmod(stream.fileno(), 384)
            stream.write(data)
        path = directory / filename
        if directory.is_symlink() or not os.path.samestat(directory.stat(), os.fstat(directory_fd)):
            raise OSError('Output directory changed while saving.')
        return path
    except Exception:
        if filename is not None:
            os.unlink(filename, dir_fd=directory_fd)
        raise
    finally:
        os.close(directory_fd)

def _bounded_output(output):
    """Bound final results once, preserving complete data in private artifacts."""
    data = output.encode('utf-8')
    if len(data) <= OUTPUT_PREVIEW_BYTES:
        return output

    preview = data[:OUTPUT_PREVIEW_BYTES].decode('utf-8', errors='ignore')
    try:
        path = _save_output(data)
    except Exception as exc:
        detail = _error_text(exc).encode('utf-8')[:1000].decode('utf-8', errors='ignore')
        return 'Error: Could not save complete output artifact; full result unavailable. The operation may have completed; verify writes before retrying.\n' + detail + '\n[TRUNCATED: output preview only; no complete artifact.]\n' + preview
    return preview + f'\n[TRUNCATED: showing at most {OUTPUT_PREVIEW_BYTES} of {len(data)} UTF-8 bytes.]\nComplete UTF-8 text: {path}\nRead this local file with file tools for the complete result.'
