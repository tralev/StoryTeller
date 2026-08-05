package com.storyteller.droid.engine

import android.content.Context
import android.media.AudioAttributes
import android.media.MediaPlayer
import java.io.File

/** Lifecycle-safe validated MIDI playback facade. */
class MidiPlayer(private val context: Context) {
    private var active: MediaPlayer? = null
    private var backgroundPaused = false
    val isPlaying get() = active?.isPlaying == true
    fun init() = Unit
    fun play(file: File, loop: Boolean = true) {
        require(file.isFile && file.length() > 0) { "MIDI_INVALID" }
        stop()
        active = MediaPlayer().apply {
            setAudioAttributes(AudioAttributes.Builder().setUsage(AudioAttributes.USAGE_MEDIA)
                .setContentType(AudioAttributes.CONTENT_TYPE_MUSIC).build())
            setDataSource(file.absolutePath); isLooping = loop; prepare(); start()
        }
    }
    fun crossfade(nextFile: File, durationMs: Long = 2_000) {
        require(durationMs >= 0); val previous = active
        val next = MediaPlayer().apply {
            setDataSource(nextFile.absolutePath); isLooping=true; setVolume(0f,0f); prepare(); start()
        }
        active=next
        val steps=20; Thread {
            for(step in 1..steps){val ratio=step.toFloat()/steps;previous?.setVolume(1-ratio,1-ratio);next.setVolume(ratio,ratio);Thread.sleep(durationMs/steps)}
            previous?.stop();previous?.release()
        }.start()
    }
    fun onBackground(){if(isPlaying){active?.pause();backgroundPaused=true}}
    fun onForeground(){if(backgroundPaused){active?.start();backgroundPaused=false}}
    fun stop(){active?.runCatching{stop()};active?.release();active=null;backgroundPaused=false}
    fun release()=stop()
}
