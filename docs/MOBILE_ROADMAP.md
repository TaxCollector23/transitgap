# Mobile roadmap

## Web experience

The existing React application uses a responsive route planner and map. The A start, B VTA stop, and R community report pin have separate labels and map selection states. The planner includes a narrow-screen sheet and a map loading state.

Before calling the mobile web experience ready, run Playwright at small phone and tablet viewports and inspect the resulting screenshots. Check selection instructions above the sheet, stop search visibility, map attribution and controls, keyboard focus, browser zoom, and error recovery.

## Native iOS and Android

The project is not a native application. Capacitor is a reasonable next step after the county deployment and web workflows are stable.

1. Add Capacitor to the existing Vite build without moving route logic into native plugins.
2. Configure deep links to `/app` and app-safe API origins.
3. Add location permission explanations and test denied, approximate, and precise location states on physical devices.
4. Evaluate MapLibre native rendering separately from the current web map; do not assume web tile or marker behavior carries over.
5. Select durable, abuse-resistant community report storage before app store release.
6. Test VoiceOver, TalkBack, reduced motion, offline behavior, and device text scaling.

Native builds, store listings, and device QA have not been produced.
