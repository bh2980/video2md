class Video2MdError(Exception):
    exit_code = 1


class UsageError(Video2MdError):
    exit_code = 2


class FfmpegNotFoundError(Video2MdError):
    exit_code = 3


class InputNotFoundError(Video2MdError):
    exit_code = 4


class CaptionParseError(Video2MdError):
    exit_code = 4


class WhisperError(Video2MdError):
    exit_code = 5


class PlatformError(Video2MdError):
    exit_code = 6


class FfmpegError(Video2MdError):
    exit_code = 1


class OcrError(Video2MdError):
    exit_code = 1
