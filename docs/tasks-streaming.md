# Zadania — strona streamingu

Kontekst: moduł percepcji (C++, korzeń repo) produkuje klatki i detekcje.
`apps/` odbiera je i dostarcza do przeglądarki. Potok działa end-to-end, ale
kilku rzeczy brakuje do użycia na dronie.

Zadania są niezależne, chyba że napisano inaczej. Kolejność w sekcji =
sugerowany priorytet.

---

## Najpierw: uruchom to u siebie

Zanim cokolwiek zmienisz, zobacz jak działa. Potok nie był jeszcze uruchomiony
w całości na jednej maszynie — jeśli coś nie zagra, to jest pierwsza rzecz do
naprawienia i reszta zadań może poczekać.

```bash
cd apps/backend && go run ./cmd/server
./run.sh                                        # wymaga modelu ONNX w models/
cd apps/client && uv sync && uv run main.py
cd apps/frontend && npm install && npm run dev
```

Bez modelu i kamery: pomiń `./run.sh`, ustaw `VIDEO_SOURCE=local` w
`apps/client/.env` i odpal `uv run mock_perception.py` — dostaniesz syntetyczne
detekcje na obrazie z własnej kamery.

Czego szukać:
- ramki nad obiektami na `/{streamId}` i czysty obraz na `/{streamId}?raw=1`
- panel telemetrii (prawy górny róg): liczba obiektów, fps, opóźnienie
- ramki zgadzają się z obiektami przy zmianie rozmiaru okna

---

## S1. Reconnect klienta — sprawdzić, czy działa pod obciążeniem

**Dlaczego:** `apps/client/main.py` ma pętlę reconnect z backoffem, ale
testowana była tylko ścieżka szczęśliwa. Na dronie zerwanie sieci to norma, nie
wyjątek.

**Co zrobić:** ubić backend w trakcie streamingu, sprawdzić czy klient wraca po
jego restarcie. To samo dla zerwania w połowie handshake'u WHIP.

**Uwaga:** backend odrzuca drugiego publishera na tym samym `stream_id`
(`ErrAlreadyPublishing`), a stary wpis znika dopiero gdy ICE przejdzie w
`failed` — to potrafi trwać ~30 s. Jeśli klient wróci szybciej, dostanie 409.
Do rozstrzygnięcia: czy nowy publisher ma przejmować strumień, czy klient ma
czekać.

**Gdzie:** `apps/client/main.py`, `apps/backend/relay/relay.go`

---

## S2. Rozdzielczość i kodek pod drona

**Dlaczego:** klient wysyła surowe klatki BGR, które `aiortc` koduje
programowo. Przy 640x480/30fps to zauważalne obciążenie CPU — a na urządzeniu
brzegowym ten sam procesor liczy YOLO.

**Co zrobić:** zmierzyć realne zużycie CPU przez enkoder na docelowym sprzęcie.
Jeśli boli, sprawdzić enkoder sprzętowy (V4L2 M2M na Linuksie,
VideoToolbox na macOS) — `aiortc` na to pozwala, ale trzeba go skłonić.

**Zależność:** ma sens dopiero gdy wiadomo, na czym to poleci.

**Gdzie:** `apps/client/camera.py`

---

## S3. Wiele strumieni naraz

**Dlaczego:** backend obsługuje wiele `stream_id`, ale nikt tego nie sprawdził z
dwoma dronami jednocześnie. `HomePage` listuje strumienie z `/streams/`, więc
UI jest gotowy.

**Co zrobić:** odpalić dwóch klientów z różnymi `STREAM_ID`, sprawdzić czy oba
widać na liście i czy przełączanie działa. Zwrócić uwagę na zużycie pamięci
przy kilku subskrybentach na strumień.

**Gdzie:** `apps/backend/relay/hub.go`

---

## S4. Zabezpieczenie backendu

**Dlaczego:** obecnie każdy może publikować i subskrybować. CORS jest ustawiony
na `*`. Do dema OK, poza siecią lokalną — nie.

**Co zrobić:** ustalić z zespołem model zagrożeń (czy to w ogóle wychodzi poza
LAN?), potem najprostsza rzecz, która wystarczy: token w nagłówku przy WHIP,
ograniczenie CORS do znanych origin.

**Uwaga:** nie komplikować przedwcześnie — jeśli to zostaje w sieci lokalnej,
sam CORS może wystarczyć.

**Gdzie:** `apps/backend/http/server.go`

---

## S5. Nagrywanie strumienia detekcji

**Dlaczego:** README modułu percepcji wskazuje brak trwałego logowania jako
ograniczenie. Ramki wysyłane na gniazdo mają komplet danych, więc zapisanie ich
daje powtarzalne testy bez kamery.

**Co zrobić:** zapis ramek do pliku (JSON Lines) i odtwarzanie ich na gniazdo z
oryginalnym taktowaniem. Efekt: da się testować front i backend na nagraniu z
prawdziwego lotu.

**Gdzie:** nowy skrypt obok `apps/client/mock_perception.py`

---

## Znane braki (do świadomej decyzji, nie do zrobienia od ręki)

**Detekcje nie są zsynchronizowane z obrazem.** `timestamp_ms` to zegar
producenta, więc nakładka wyprzedza wideo o opóźnienie transmisji — dziesiątki
do setek ms. Widać to przy szybkim ruchu. Naprawa wymaga wspólnej osi czasu
przeniesionej przez potok WebRTC; do monitoringu obecny stan wystarcza.

**Pamięć współdzielona nie przechodzi przez sieć.** Klient musi działać na tym
samym urządzeniu co moduł percepcji. Odbiorca zdalny bierze obraz z WebRTC.

**Backend nie waliduje detekcji.** Przekazuje bajty, nie parsuje JSON-a. Zaleta:
zmiana formatu nie wymaga wdrożenia backendu. Wada: błędna ramka wyjdzie na jaw
dopiero w przeglądarce (front ją odrzuci, ale po cichu).

---

## Gdzie co jest

| Ścieżka | Co |
| --- | --- |
| `apps/backend/relay/` | rozgłaszanie RTP i detekcji, sesje |
| `apps/client/frame_shm.py` | odczyt klatek z modułu percepcji |
| `apps/client/camera.py` | źródła wideo (moduł / lokalna kamera) |
| `apps/client/detection_source.py` | odbiór detekcji z gniazda |
| `apps/frontend/src/DetectionOverlay.tsx` | rysowanie ramek na wideo |
| `docs/detection-protocol.md` | format ramek |
| `docs/consuming-streams.md` | jak napisać własnego odbiorcę |
