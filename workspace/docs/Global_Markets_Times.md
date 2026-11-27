Czasy rynkowe w ujęciu globalnym (planowane do implementacji w Honey-Barrel Labs)
===================================================================================

Godzina (CEST)	    Regime	        Kolor
-----------------------------------------
00:00–02:00	        PACIFIC	        Niebieski ciemny
02:00–09:00	        ASIA	          Pomarańczowy
09:00–15:30	        EUROPE	        Zielony
15:30–17:30	        EUROPE + US	    Zielony jasny + pulsujący
17:30–22:00	        US	            Niebieski cyan + animacja
22:00–00:00	        US AFTER-HOURS	Fioletowy       
Weekendy	          WEEKEND	        Czerwony

CEST = Central European Summer Time (UTC+2) bardziej szczegółowo: https://www.timeanddate.com/time/zones/cest
00:00   ├── 🇳🇿 NZ
02:00       ├── 🇦🇺 Australia
02:00       ├── 🇯🇵 Tokyo
03:30           ├── 🇨🇳 China
03:30           ├── 🇭🇰 Hong Kong
05:45               ├── 🇮🇳 India
09:00                           ├── 🇩🇪 🇫🇷 EUROPE
09:00                           ├── 🇬🇧 London
15:30                                                   ├── 🇺🇸 NYSE/NASDAQ
22:00                                                               └── USA CLOSE

🔥 Najważniejsze są trzy fazy
+++++++++++++++++++++++++++++

1. Asia — ~02:00–10:00

Najważniejsze:

Nikkei
TOPIX
Hang Seng
Shanghai / Shenzhen
ASX

Największe znaczenie dla:

JPY
CNY
AUD
półprzewodników
spółek technologicznych
surowców

2. Europe — ~09:00–17:30

Tu zaczyna się bardzo istotna część globalnego price discovery:

DAX
CAC 40
FTSE 100
Euro Stoxx 50
IBEX
FTSE MIB
WIG20

Szczególnie interesujące jest:

🇬🇧 London Open — 09:00 PL

oraz:

🇺🇸 NYSE/Nasdaq Open — 15:30 PL


⚡ To najważniejszy moment dnia: 15:30–17:30
  Wtedy następuje overlap Europy i USA:

09:00 ─────────────────────── 17:30
       EUROPE
       █████████████████████████████

15:30                    USA
                         █████████████████████████████

                           ▲
                           │
                     15:30–17:30
                       OVERLAP

To zazwyczaj najbardziej interesujące okno dla systemu typu Investment Analyst, ponieważ jednocześnie aktywne są:

Frankfurt
London
Paris
Amsterdam
New York
Nasdaq
Toronto

i pojawia się dużo większy przepływ informacji oraz kapitału.

Dla każdego tickera można wtedy określić, który rynek jest właśnie źródłem price discovery.

Przykładowo:

NVDA
│
├── Asia       → futures / ADR / semiconductor sentiment
├── Europe     → futures + European semiconductor complex
├── US Open    → primary price discovery
├── US Session → primary liquidity
└── Afterhours → earnings/news driven

To może być bardzo użyteczne dla Twojego Watchlist Retraining Monitor — model może dostać informację nie tylko co się dzieje z ceną, ale w której fazie globalnego cyklu rynkowego to się dzieje.

TBC.. CDN..


