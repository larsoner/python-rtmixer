#!/usr/bin/env python3
"""A minimalistic sampler with an even more minimalistic GUI."""

import collections
import functools
import math
try:
    import tkinter as tk
except ImportError:
    import Tkinter as tk  # Python 2.x

import rtmixer
import tkhelper


HELPTEXT = 'Hold uppercase key for recording,\nlowercase for playback'
REC_OFF = '#600'
REC_ON = '#e00'
BUFFER_DURATION = 0.1  # seconds


class Sample(object):

    def __init__(self, elementsize, size):
        # Python 2.x doesn't have math.log2(), and it needs int():
        size = 2**int(math.ceil(math.log(size, 2)))
        self.ringbuffer = rtmixer.RingBuffer(elementsize, size)
        self.buffer = bytearray()
        self.action = None


class MiniSampler(tk.Tk, tkhelper.KeyEventDebouncer):

    def __init__(self, stream, buffer_duration=BUFFER_DURATION):
        tk.Tk.__init__(self)
        tkhelper.KeyEventDebouncer.__init__(self)
        self.title('MiniSampler')
        tk.Label(self, text=HELPTEXT).pack(ipadx=20, ipady=20)
        self.rec_display = tk.Label(self, text='recording')
        self.rec_counter = tkhelper.IntVar()
        self.rec_counter.trace(mode='w', callback=self.update_rec_display)
        self.rec_counter.set(0)
        self.rec_display.pack(padx=10, pady=10, ipadx=5, ipady=5)
        self.samples = collections.defaultdict(functools.partial(
            Sample, stream.samplesize[0], buffer_duration * stream.samplerate))
        self.stream = stream

    def update_rec_display(self, *args):
        if self.rec_counter.get() == 0:
            self.rec_display['bg'] = REC_OFF
        else:
            self.rec_display['bg'] = REC_ON

    def on_key_press(self, event):
        ch = event.char
        if ch.isupper():
            sample = self.samples[ch.lower()]
            if sample.action in self.stream.actions:
                return
            if sample.ringbuffer.read_available:
                return
            del sample.buffer[:]
            self.rec_counter += 1
            sample.action = self.stream.record_ringbuffer(sample.ringbuffer)
            self.poll_ringbuffer(sample)
        elif ch in self.samples:
            sample = self.samples[ch]
            if sample.action in self.stream.actions:
                # CANCEL action from last key release might still be active
                return
            sample.action = self.stream.play_buffer(sample.buffer, channels=1)

    def on_key_release(self, event):
        # NB: State of "shift" button may change between key press and release!
        ch = event.char.lower()
        if ch not in self.samples:
            return
        sample = self.samples[ch]
        # TODO: fade out (both recording and playback)?
        assert sample.action is not None
        if sample.action.type == rtmixer.RECORD_RINGBUFFER:
            # TODO: check for errors/xruns? check for rinbuffer overflow?
            # Stop recording
            sample.action = self.stream.cancel(sample.action)
            # A CANCEL action is returned which is checked by poll_ringbuffer()
        elif sample.action.type == rtmixer.PLAY_BUFFER:
            # TODO: check for errors/xruns?
            # Stop playback (if still running)
            if sample.action in self.stream.actions:
                sample.action = self.stream.cancel(sample.action)
                # TODO: do something with sample.action?
        elif sample.action.type == rtmixer.CANCEL:
            # We might end up here if on_key_press() exits early
            pass
        else:
            assert False, (event.char, sample.action)

    def poll_ringbuffer(self, sample):
        assert sample.action is not None
        assert sample.action.type in (rtmixer.RECORD_RINGBUFFER,
                                      rtmixer.CANCEL)
        # TODO: check for errors? is everything still working OK?
        # TODO: check for xruns?
        chunk = sample.ringbuffer.read()
        if chunk:
            sample.buffer.extend(chunk)

        if sample.action not in self.stream.actions:
            # Recording is finished
            # TODO: check for errors in CANCEL action?
            self.rec_counter -= 1
        else:
            # Set polling rate based on input latency (which may change!):
            self.after(int(self.stream.latency[0] * 1000),
                       self.poll_ringbuffer, sample)


def main():
    with rtmixer.MixerAndRecorder(channels=1) as stream:
        app = MiniSampler(stream)
        app.mainloop()


if __name__ == '__main__':
    main()