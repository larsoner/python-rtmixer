"""Reliable low-latency audio playback and recording."""
__version__ = '0.0.0'

import sounddevice as _sd
from _rtmixer import ffi as _ffi, lib as _lib


# TODO: mixer class without inputs (kind='output')


class RtMixer(_sd._StreamBase):
    """PortAudio stream with realtime mixing callback."""

    def __init__(self, channels, blocksize=1024, **kwargs):
        """Create a realtime mixer object.

        Takes the same keyword arguments as `sounddevice.Stream`, except
        *callback* and *dtype*.

        In contrast to `sounddevice.Stream`, the *channels* argument is
        not optional.

        Uses default values from `sounddevice.default`.

        """
        callback = _ffi.addressof(_lib, 'callback')
        input_channels, output_channels = _sd._split(channels)

        # TODO: allow blocksize=0

        # TODO: parameter for ring buffer size
        rb_size = 512

        self._rb = RingBuffer(
            _ffi.sizeof('float') * output_channels * blocksize, rb_size)

        userdata = _ffi.new('state_t*', dict(
            input_channels=input_channels,
            output_channels=output_channels,
            rb_ptr=self._rb._ptr,
        ))
        self._userdata = userdata  # Keep alive
        super(RtMixer, self).__init__(
            kind=None, wrap_callback=None,
            blocksize=blocksize, channels=channels,
            dtype='float32', callback=callback, userdata=userdata, **kwargs)

    def enqueue_numpy(self, array):
        # TODO: check shape
        while not self._rb.write_available:
            _sd.sleep(250)
        ret = self._rb.write(array)
        if ret != 1:
            print("Error writing to ring buffer")


class RingBuffer(object):
    """Wrapper for PortAudio's ring buffer.

    See __init__().

    """

    def __init__(self, elementsize, size):
        """Create an instance of PortAudio's ring buffer.

        Parameters
        ----------
        elementsize : int
            The size of a single data element in bytes.
        size : int
            The number of elements in the buffer (must be a power of 2).

        """
        self._ptr = _ffi.new('PaUtilRingBuffer*')
        self._data = _ffi.new('unsigned char[]', size * elementsize)
        res = _lib.PaUtil_InitializeRingBuffer(
            self._ptr, elementsize, size, self._data)
        if res != 0:
            assert res == -1
            raise ValueError('size must be a power of 2')
        assert self._ptr.bufferSize == size
        assert self._ptr.elementSizeBytes == elementsize

    def flush(self):
        """Reset buffer to empty.

        Should only be called when buffer is NOT being read or written.

        """
        _lib.PaUtil_FlushRingBuffer(self._ptr)

    @property
    def write_available(self):
        """Number of elements available in the ring buffer for writing."""
        return _lib.PaUtil_GetRingBufferWriteAvailable(self._ptr)

    @property
    def read_available(self):
        """Number of elements available in the ring buffer for reading."""
        return _lib.PaUtil_GetRingBufferReadAvailable(self._ptr)

    def write(self, data, size=-1):
        """Write data to the ring buffer.

        Parameters
        ----------
        data : CData pointer or buffer or bytes
            Data to write to the buffer.
        size : int, optional
            The number of elements to be written.

        Returns
        -------
        int
            The number of elements written.

        """
        try:
            data = _ffi.from_buffer(data)
        except AttributeError:
            pass  # from_buffer() not supported
        except TypeError:
            pass  # input is not a buffer
        if size < 0:
            size, rest = divmod(len(data), self._ptr.elementSizeBytes)
            if rest:
                raise ValueError('data size must be multiple of elementsize')
        return _lib.PaUtil_WriteRingBuffer(self._ptr, data, size)

    def read(self, data, size=-1):
        """Read data from the ring buffer.

        Parameters
        ----------
        data : CData pointer or buffer
            The memory where the data should be stored.
        size : int, optional
            The number of elements to be read.

        Returns
        -------
        int
            The number of elements read.

        """
        try:
            data = _ffi.from_buffer(data)
        except AttributeError:
            pass  # from_buffer() not supported
        except TypeError:
            pass  # input is not a buffer
        if size < 0:
            size, rest = divmod(len(data), self._ptr.elementSizeBytes)
            if rest:
                raise ValueError('data size must be multiple of elementsize')
        return _lib.PaUtil_ReadRingBuffer(self._ptr, data, size)
