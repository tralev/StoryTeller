# StoryTeller Target Accessibility

## Goal

The Player and thin Forge launcher should be usable with platform assistive
technology without weakening mature-content disclosures, story integrity, or GM
privacy. Accessibility is a release requirement, not post-release polish.

## Standards target

- Follow current Apple and Android accessibility guidance.
- Use WCAG 2.2 AA principles where applicable to mobile/desktop application UI.
- Test with VoiceOver and TalkBack on physical devices.
- Respect platform text size, contrast, reduced motion, audio, and input settings.

Formal compliance claims require a release-time audit; this document defines
engineering behavior, not certification.

## Player navigation

- Every screen has a stable accessible title and logical focus order.
- Library stories, nodes, choices, endings, GM controls, and deletion dialogs are
  reachable without gestures that require precision.
- Back behavior is predictable and never discards a choice/save silently.
- Touch targets meet platform minimums and do not overlap.
- Current node/choice state is conveyed by semantics, not color alone.
- Screen-reader focus moves deliberately after navigation, import completion,
  error display, and GM stream completion.

## Text and reading

- Support platform dynamic type/font scaling without clipping or horizontal
  scrolling of prose and choices.
- Preserve meaningful paragraph/line structure for screen readers.
- Allow user-selected readable font, line spacing, and theme where feasible.
- Maintain AA contrast for text and interactive states.
- Do not encode flags, endings, warnings, or selected choices using color alone.
- Mature-content and AI disclosures are readable before content interaction.

## Images and maps

- Every node image has concise generated or authored alternative text derived
  from accepted narrative metadata, not raw image prompt boilerplate.
- Decorative thumbnails do not duplicate announcements when the story title is
  already labeled.
- World/region maps have structured summaries: region names, neighbors, current
  story location, and relevant routes. Raw pixel maps alone are insufficient.
- Zoom/pan controls are accessible and have non-gesture alternatives if a map UI
  is introduced later.
- Image absence is impossible in accepted v2, but decode/display failure still
  produces accessible diagnostic text.

## MIDI and audio

- Reading does not require hearing the MIDI.
- Provide play/pause, volume, and music-disable controls with accessible labels.
- Respect system audio interruptions and user preference across nodes/restarts.
- Crossfades do not produce sudden excessive volume.
- Do not autoplay over active screen-reader speech when platform guidance advises
  against it; provide a persistent preference.

## Choices and state

- Announce choice text, availability, and disabled requirement without exposing
  hidden future consequences.
- Conditional text is inserted in a way screen readers perceive once, in order.
- Ending type/title and restart options are structured as headings/actions.
- Save progress automatically; accessibility users should not face additional
  manual-save requirements.

## Game Master chunks

- Do not announce every model token or tiny chunk.
- Buffer chunks into sentence/phrase-sized accessible updates or announce only
  completion according to user preference.
- Show continuous visual progress without repeatedly stealing accessibility focus.
- Provide Pause/Cancel/Retry with clear request state.
- Completed user and assistant turns expose correct semantic roles and order.
- History clear and local flag/export actions require confirmation and explain
  their local-only effect.

## Import and model download

- File picker, validation progress, v1 rejection, and errors are announced.
- Model name, size, license, network/storage requirement, progress, cancellation,
  checksum failure, and retry are available to screen readers.
- Progress has a semantic value, not only animation.
- Do not rely on time-limited dialogs for consent or error recovery.

## Motion and visual effects

- Respect reduced-motion settings.
- Replace page transitions, pulsing progress, and parallax with non-motion states.
- Avoid flashing content.
- Dark-fantasy aesthetics must not reduce contrast or obscure controls.
- Support light/dark/high-contrast platform modes where practical.

## Thin desktop launcher

- Complete keyboard navigation and visible focus
- Native labels for every form control and validation issue
- Progress text alongside bars/colors
- Copyable error codes and diagnostic paths
- Cancel/resume/result controls reachable without mouse
- Wine test with keyboard and at least one supported accessibility strategy;
  toolkit choice must not make core controls inaccessible by design

## Localization readiness

The first release may be English-only, but strings must not be embedded in data
logic. Use localization resources, avoid concatenated sentences, allow expansion,
and keep package/entity IDs separate from display text. Generated story language
and application UI language are distinct configuration concerns.

## Accessibility data and privacy

Do not log accessibility settings, spoken content, questions, or GM answers.
Platform accessibility APIs must not trigger network behavior or telemetry.

## Test matrix

- VoiceOver on minimum and representative iOS devices
- TalkBack on minimum and representative Android devices
- Maximum supported text size
- High contrast and dark/light modes
- Reduced motion
- Switch/keyboard navigation where platform supports it
- Screen reader during MIDI playback and GM chunks
- Import/model download errors
- Long titles, choices, errors, and translated-string expansion fixtures
- Offline mode

## Release checklist

- [ ] All interactive controls have meaningful labels, roles, states, and actions.
- [ ] Focus order and post-navigation focus are intentional.
- [ ] Dynamic text does not clip critical content/actions.
- [ ] Contrast and non-color state communication pass review.
- [ ] Images/maps have useful non-spoiling alternatives.
- [ ] Story remains understandable with music disabled.
- [ ] GM chunk announcements are usable and cancellable.
- [ ] Model download/import flows are fully accessible.
- [ ] Reduced motion and audio preferences are respected.
- [ ] Physical VoiceOver and TalkBack evidence is attached to the release record.

