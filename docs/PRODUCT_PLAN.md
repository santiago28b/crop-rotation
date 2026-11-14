# Field Shift: Product and UI Plan

_Planning draft — November 14, 2026_

## Decisions confirmed so far

- The initial audience is farmers with fewer resources; the first version is not Idaho-specific.
- This is a hackathon project with limited build time, so the first release should stay narrow and demoable.
- The frontend is built in Vue and the backend uses FastAPI. Their shared contracts and local run steps are documented in the repository README and backend API docs.
- Weak connectivity and offline support are out of scope for the initial build.

## Purpose

Help a farmer understand which crops may fit a particular field and make a practical, field-specific growing plan. The product should make complex data approachable for people with different language, reading, and technology skills. It is decision support; farmers remain in control of their choices.

## Current concept

1. A user signs in (the authentication flow is still to be defined).
2. They add a field by drawing its boundary on a map.
3. They enter farm resources and constraints in a profile.
4. The app estimates the field's crop history for the previous five years. The user can correct it.
5. The app combines field, resource, crop-history, and environmental information to show suitable crop options.
6. The user chooses a crop and asks the app to generate a plan with timing and care guidance, including planting and watering.

The README describes the original Treasure Valley comparison concept. The current target is broader: farmers with fewer resources, without an Idaho-only focus. NASA POWER, OpenET, GRACE/GRACE-FO, USGS, SMAP, SSURGO, CropScape (USDA), and MODIS NDVI remain planned or active sources at different levels of coverage. Crop history comes from USDA CropScape/Crop Data Layer in the continental US; elsewhere, the farmer enters it.

## Product principles

- **Easy to understand at a glance:** use large tap targets, strong visual hierarchy, familiar symbols, and short sentences.
- **Icons plus words:** icons should reinforce meaning, never be the only way to understand an action. Use accessible names for screen readers.
- **Show the farmer what the app knows:** identify estimates, sources, dates, and uncertainty. Make corrections easy.
- **Keep the farmer in control:** explain why a recommendation appears and let the user compare, edit, or decline it.
- **Design for real conditions:** mobile use, bright outdoor light, and users with varied vision, reading ability, language, and digital experience should be considered. Offline and weak-connectivity support are deferred for the hackathon build.
- **Avoid false precision:** recommendations and schedules depend on local conditions and farm choices. Show assumptions and ask for missing inputs instead of implying certainty.

## Proposed user journey and screens

### 1. Welcome and account

Explain the app in a few plain-language steps. Offer sign-in and account creation, with a clear way to recover access. Ask for language preference early. Avoid requiring profile details that are not needed to start.

### 2. Home / farm overview

Show the user's farms and fields as clear cards with field names, area, and a recognizable status (for example, needs information, ready to explore, or plan available). Make the primary next action prominent: add a field or continue setup.

### 3. Add a field

Let the user search for a place or use their device location, then draw and adjust a field boundary on the map. Provide large, labeled controls for drawing, undoing, clearing, and saving. Show calculated area and ask the user to confirm the boundary. Include an accessible non-map way to identify a field if feasible (for example, address/location search or coordinate entry); determine its priority with users.

### 4. Farm resources and field details

Collect only the details needed for useful recommendations. Potential fields include irrigation/water access, soil information, equipment or labor limits, preferred crops, market or contract needs, and growing practices. Prefer visual choices and examples where helpful, while allowing “I don't know” and “skip for now.” Explain why each requested item matters.

### 5. Crop history review

Show one year at a time for the past five years, with the estimated crop, confidence or “not sure” state, and a simple way to edit it. Clearly distinguish an estimated result from a farmer-confirmed value. Ask how the user wants to handle missing years, multiple crops, cover crops, fallow years, and uncertain classifications.

### 6. Crop options

Present a manageable set of options as visual cards. Each should answer: why it may fit, what resources it needs, expected tradeoffs, and what data or assumptions shaped the result. Allow side-by-side comparison and a way to revisit inputs. Confirm whether the product recommends a single crop, a rotation sequence, or both.

### 7. Generate and review a plan

After a user selects an option, generate a field-specific calendar or sequence of tasks. Candidate tasks include planting, irrigation, monitoring, and harvest, but the exact scope and level of detail are open. Show dates as ranges or conditions when exact dates are uncertain. Let the user adjust the plan and save, print, or share it if those are in scope.

### 8. Return visits

Allow users to revisit fields, update resources and crop history, and see which plans or recommendations have changed. Decide whether reminders, seasonal check-ins, and multiple users per farm are needed.

## UI scope for this phase

The user's stated role is frontend/UI. The first design/build phase should therefore focus on:

- Mapping the main user journey and screen states.
- Establishing a reusable visual system for large buttons, icon-plus-label actions, readable type, color, spacing, and responsive layouts.
- Designing loading, no-data, error, low-confidence, and incomplete-setup states.
- Making map drawing and crop-history correction understandable and forgiving.
- Showing how recommendations and plans explain their reasoning and uncertainty.
- Defining the frontend data contracts and integration assumptions with whoever owns backend, auth, and data services; do not imply those services already exist.

The Vue frontend now uses the FastAPI profile, history, insights, crop catalog, and report endpoints. Keep loading, unavailable-data, and API-error states visible because upstream data can be slow or unavailable.

## Decisions and questions for the product owner

### Users and geography

1. Who is the primary user: owner/operator, farm worker, agronomist, or another role? Can one account serve several roles?
2. Which initial country or region should the demo represent, given that the target is broader than Idaho?
3. Are users managing small gardens, commercial fields, or both? What are typical field sizes?
4. Should a farm have multiple fields, and should multiple people share a farm or field?

### Languages and accessibility

5. Which languages should the first version support? Should language be selected during onboarding or follow device settings?
6. Who are the first users you can ask to try the UI, including people with limited English or limited comfort with apps?
7. What does “doesn't know a lot about technology” mean for your target users: should we assume little map experience, limited email access, shared devices, or something else?
8. Should every important action have both an icon and a text label? (Recommended for clarity.)
9. Are voice instructions, audio playback, translated help, or a guided step-by-step mode important for the first version?
10. Is the app primarily used on a phone in the field, on a desktop, or both? (Offline support is deferred for the first build.)

### Account and farm setup

11. Which sign-in options do you expect (email/password, phone, Google/Apple, or another method)? Do users need to use the product before creating an account?
12. What does “resource information” mean in your mind? Which exact resources or constraints should the profile ask about?
13. Should profile information apply to the whole farm, an individual field, or both? Can users skip unknown answers?

### Map and field

14. Should users search an address/place, use GPS, draw a polygon, select parcel boundaries, or use more than one of these?
15. Do you want to support irregular field shapes, multiple disconnected plots, and editing a saved boundary?
16. Should the app calculate field area and show units in acres, hectares, or let users choose?
17. What should happen when the field is outside supported data coverage or the map cannot locate it?

### Crop history and data

18. Is the five-year crop history meant to be detected automatically, or should the app propose likely crops for the farmer to confirm?
19. The README currently lists USDA CropScape/Crop Data Layer for crop history. Is USDA data acceptable for that feature, or is NASA-only data a requirement?
20. How should the UI handle a missing/uncertain year, multiple crops in one field, cover crops, or fallow land?
21. Should the farmer be able to edit the crop history at any time and see which values came from the farmer versus a data estimate?

### Recommendations and generated plan

22. Should the app suggest a crop for one season, a multi-year crop rotation, or both?
23. How many recommendations should be shown at once? The README currently proposes three rotation comparisons.
24. What should “best” mean: water availability, soil health, yield potential, profitability, risk reduction, farmer preference, or a weighted mix?
25. Which crops should be in scope, and are there crops the product should never recommend?
26. What does “generate plan” need to produce: planting window, irrigation schedule, task calendar, fertilizer/pest guidance, harvest window, or something else?
27. Should generated plans be editable, printable, downloadable, shareable, or exportable to a calendar?
28. How should the app communicate confidence and uncertainty so recommendations are useful without sounding guaranteed?

### Project boundaries and next step

29. Who will own backend, data, and authentication work, if anyone?
30. Which map provider and design tools (if any) are already chosen? (Frontend: Vue; backend: Python.)
31. What would make the first UI milestone successful: a clickable prototype, a polished set of screens, or a working frontend connected to mock data?
32. Is there a demo deadline or required judging/demo flow we should plan around?

## Suggested first milestone

Keep the first build focused on a small, demoable Vue experience using realistic mock data. Resolve the initial demo geography, screen set, and visual direction; then validate the clickable flow with intended users, especially someone who is not comfortable navigating typical apps. Defer offline support and detailed backend/data integration decisions.

## Not yet specified

Authentication, persistent farm accounts, multi-user access, a generated task calendar, and offline support are still outside the current integrated flow. The backend returns field profiles, ranked crop candidates, and a separate profit comparison; it does not yet generate a full farm work plan.
