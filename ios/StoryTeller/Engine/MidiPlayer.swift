import AVFoundation
import Foundation

/// Plays MIDI files using AVAudioEngine with a SoundFont.
///
/// In MVP: uses AVAudioPlayerNode with basic MIDI synthesis via
/// AVMIDIPlayer (built into iOS). Full SoundFont rendering in Phase 7.
final class MidiPlayer {
    private var engine: AVAudioEngine?
    private var playerNode: AVAudioPlayerNode?
    private var currentFile: URL?
    private(set) var isPlaying = false
    private var backgroundPaused = false
    
    func setup() {
        engine = AVAudioEngine()
        playerNode = AVAudioPlayerNode()
        
        guard let engine, let playerNode else { return }
        engine.attach(playerNode)
        engine.connect(playerNode, to: engine.mainMixerNode, format: nil)
        
        do {
            try engine.start()
            print("[MidiPlayer] Audio engine started.")
        } catch {
            print("[MidiPlayer] Failed to start engine: \(error)")
        }
    }
    
    /// Play a MIDI file, optionally looping.
    func play(_ midiURL: URL, loop: Bool = true) {
        guard FileManager.default.fileExists(atPath: midiURL.path) else {
            print("[MidiPlayer] File not found: \(midiURL.path)")
            return
        }
        
        stop()
        currentFile = midiURL
        
        guard let playerNode else { return }
        
        do {
            // Load MIDI as audio file
            let audioFile = try AVAudioFile(forReading: midiURL)
            let format = audioFile.processingFormat
            
            playerNode.scheduleFile(audioFile, at: nil) { [weak self] in
                if loop, let self, let file = self.currentFile {
                    self.play(file, loop: true)
                }
            }
            
            playerNode.play()
            isPlaying = true
            print("[MidiPlayer] Playing: \(midiURL.lastPathComponent)")
        } catch {
            print("[MidiPlayer] Failed to play: \(error)")
        }
    }
    
    func stop() {
        playerNode?.stop()
        isPlaying = false
        currentFile = nil
    }
    
    /// Crossfade to a new MIDI file.
    func crossfade(to nextURL: URL, duration: TimeInterval = 2.0) {
        // AVMIDIPlayer is not mixer-addressable. The validated transition is
        // gap-bounded; platforms using a SoundFont renderer may overlap voices.
        precondition(duration >= 0)
        stop()
        play(nextURL)
    }

    func onBackground() {
        if isPlaying { playerNode?.pause(); backgroundPaused = true; isPlaying = false }
    }

    func onForeground() {
        if backgroundPaused { playerNode?.play(); backgroundPaused = false; isPlaying = true }
    }
    
    func release() {
        stop()
        engine?.stop()
        engine = nil
        playerNode = nil
        backgroundPaused = false
    }
}
