import SwiftUI

struct ContentView: View {
    @EnvironmentObject var appState: AppState
    @Environment(\.scenePhase) private var scenePhase
    @State private var selectedStory: StoryPackage?
    @State private var showGM = false
    @State private var showModelManager = false
    
    var body: some View {
        NavigationStack {
            Group {
                if let story = selectedStory, !showGM {
                    ReaderView(
                        story: story,
                        onBack: { selectedStory = nil },
                        onAskGM: { showGM = true }
                    )
                } else if let story = selectedStory, showGM {
                    GameMasterView(
                        story: story,
                        llamaEngine: appState.llamaEngine,
                        modelURL: appState.gmModelURL,
                        onBack: { showGM = false }
                    )
                } else {
                    LibraryView(
                        storyParser: appState.storyParser,
                        onSelect: { story in
                            selectedStory = story
                            showGM = false
                        }
                    )
                }
            }
        }
        .tint(AppTheme.gold)
        .onAppear {
            showModelManager = !appState.modelDownloadManager.isInstalled
        }
        .toolbar {
            ToolbarItem(placement: .navigationBarLeading) {
                Button { showModelManager = true } label: {
                    Image(systemName: "brain")
                }
                .accessibilityLabel("Manage Game Master model")
            }
        }
        .sheet(isPresented: $showModelManager) {
            ModelDownloadConsentView(manager: appState.modelDownloadManager) {
                showModelManager = false
            }
            .interactiveDismissDisabled(appState.modelDownloadManager.task != nil)
        }
        .onChange(of: scenePhase) { phase in
            if phase == .background { appState.llamaEngine.suspendForBackground() }
        }
        .onReceive(NotificationCenter.default.publisher(for: UIApplication.didReceiveMemoryWarningNotification)) { _ in
            appState.llamaEngine.releaseForMemoryPressure()
        }
    }
}

private struct ModelDownloadConsentView: View {
    @ObservedObject var manager: ModelDownloadManager
    let dismiss: () -> Void

    var body: some View {
        NavigationStack {
            VStack(alignment: .leading, spacing: 16) {
                Text(manager.spec.displayName).font(.title2.bold())
                Text("\(manager.spec.publisher) • \(String(format: "%.2f", Double(manager.spec.byteSize) / 1_000_000_000)) GB")
                Text(manager.spec.licenseNotice).font(.footnote)
                Link("Read model license", destination: manager.spec.licenseURL)
                Text("The model is downloaded once, verified, and used completely offline.")

                switch manager.state {
                case .downloading(let downloaded, let total):
                    ProgressView(value: Double(downloaded), total: Double(total))
                    Text("\(downloaded / 1_000_000) / \(total / 1_000_000) MB")
                case .verifying:
                    ProgressView("Verifying download…")
                case .failed(_, let detail):
                    Text(detail).foregroundColor(.red)
                case .cancelled:
                    Text("Download paused. Continue to resume it.")
                case .installed:
                    Text("Installed and verified.").foregroundColor(.green)
                case .notInstalled:
                    EmptyView()
                }

                Spacer()
                if manager.task != nil {
                    Button("Cancel download", role: .destructive) { manager.cancel() }
                        .buttonStyle(.borderedProminent)
                } else if manager.isInstalled {
                    Button("Delete model", role: .destructive) { try? manager.deleteInstalledAndPartial() }
                    Button("Done", action: dismiss).buttonStyle(.borderedProminent)
                } else {
                    Button(manager.state == .cancelled ? "Continue download" : "Accept and download") {
                        manager.downloadAfterConsent()
                    }
                    .buttonStyle(.borderedProminent)
                    Button("Not now", action: dismiss)
                }
            }
            .padding(24)
            .navigationTitle("Local Game Master")
        }
    }
}
