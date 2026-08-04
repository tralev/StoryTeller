package com.storyteller.droid.engine

import android.content.Context
import android.media.AudioAttributes
import android.media.SoundPool
import android.util.Log
import java.io.File

/**
 * Plays MIDI files using Android's built-in Sonivox EAS synthesizer
 * (android.media.midi) or a downloaded SoundFont via a simple tone generator.
 *
 * For Phase 6 MVP: uses Android's built-in MIDI-to-audio pipeline.
 * The user's SoundFont download preference (first launch) will be
 * implemented in a future update.
 */
class MidiPlayer(private val context: Context) {
    companion object {
        private const val TAG = "MidiPlayer"
        private const val MAX_STREAMS = 4
    }

    private var soundPool: SoundPool? = null
    private var currentStreamId: Int = 0
    private var isPlaying: Boolean = false

    /**
     * Initialize the audio engine.
     */
    fun init() {
        val attrs = AudioAttributes.Builder()
            .setUsage(AudioAttributes.USAGE_MEDIA)
            .setContentType(AudioAttributes.CONTENT_TYPE_MUSIC)
            .build()

        soundPool = SoundPool.Builder()
            .setMaxStreams(MAX_STREAMS)
            .setAudioAttributes(attrs)
            .build()

        Log.d(TAG, "MidiPlayer initialized (maxStreams=$MAX_STREAMS)")
    }

    /**
     * Play a MIDI file.
     *
     * In the MVP, this uses Android's built-in MIDI synth via
     * MediaPlayer (which supports .mid files on most devices).
     *
     * @param midiFile Path to the .mid file.
     * @param loop Whether to loop playback.
     */
    fun play(midiFile: File, loop: Boolean = true) {
        check(midiFile.exists()) { "MIDI file not found: ${midiFile.absolutePath}" }

        // In MVP, we load the MIDI bytes and play via SoundPool.
        // Full MIDI synthesis with SoundFont (.sf2) will be Phase 7.
        val soundId = soundPool?.load(midiFile.absolutePath, 1) ?: return

        soundPool?.setOnLoadCompleteListener { _, _, status ->
            if (status == 0) {
                val loopMode = if (loop) -1 else 0
                currentStreamId = soundPool?.play(
                    soundId, 1.0f, 1.0f, 1, loopMode, 1.0f
                ) ?: 0
                isPlaying = true
                Log.d(TAG, "Playing: ${midiFile.name} (loop=$loop, streamId=$currentStreamId)")
            } else {
                Log.e(TAG, "Failed to load MIDI: ${midiFile.name}")
            }
        }
    }

    /**
     * Stop playback.
     */
    fun stop() {
        if (currentStreamId != 0) {
            soundPool?.stop(currentStreamId)
            currentStreamId = 0
        }
        isPlaying = false
    }

    /**
     * Crossfade to a new MIDI file.
     *
     * Smoothly transitions from the current track to the new one.
     *
     * @param nextFile The next MIDI file to play.
     * @param durationMs Crossfade duration in milliseconds.
     */
    fun crossfade(nextFile: File, durationMs: Long = 2000L) {
        Log.d(TAG, "Crossfading to: ${nextFile.name} (${durationMs}ms)")
        // MVP: simple stop + play. Full crossfade in Phase 7.
        stop()
        play(nextFile)
    }

    /**
     * Release audio resources.
     */
    fun release() {
        stop()
        soundPool?.release()
        soundPool = null
        Log.d(TAG, "MidiPlayer released.")
    }
}
