# Panasonic Comfort Cloud Reliable – asennus

Versio 0.1.1 on kokeellinen ensiversio. Automaattiset testit eivät korvaa testiä oikealla Panasonic-laitteella. Luotettavuutta verrattuna Socklessin integraatioon ei ole vielä mitattu.

## Panasonicin oma energiaseuranta

**Päivän sähkönkulutus haetaan suoraan Panasonic Comfort Cloudin omasta energiahistoriasta.**
`Energy today` näyttää Panasonicin pilven palauttaman päiväkulutuksen kilowattitunteina.
Tämän pilviarvon hakeminen ei vaadi erillistä sähkömittaria.
Lämmitys- ja jäähdytyssähkön päiväkulutus muodostetaan samasta kokonaisarvosta
Panasonicin palauttamien kelvollisten käyttötilaosuuksien avulla.

Panasonic määrittelee sovelluksensa kulutusluvut [arvioiksi](https://www.panasonic.com/global/hvac-cc/products/comfort-cloud/how-to-use-comfort-cloud/check-air-conditioner-energy-consumption.html).
Arvot voivat päivittyä viiveellä, ja saatavuus riippuu laitemallista sekä pilvivastauksesta.
Multi-split-järjestelmän sisäyksiköt voivat näyttää saman koko järjestelmän kulutuksen.
Ota **AC energy history** käyttöön integraation asetuksista; oletushakuväli on 15 minuuttia.
Energiatuki koskee tässä versiossa tuettuja ilmalämpöpumppuja / ilmastointilaitteita.
Oikean laitteen energia-arvojen saatavuus aikavyöhykekorjauksen jälkeen odottaa vielä vahvistusta.

## Home Assistant / Raspberry Pi 5

1. Käytä Home Assistant Core 2026.10.1:tä tai uudempaa. Testattu ohjelmistoympäristö on 2026.10.1.
2. HACS → valikko → Custom repositories.
3. Lisää `https://github.com/artepe/panasonic-comfort-cloud-reliable`, tyyppi **Integration**.
4. Lataa integraatio ja käynnistä Home Assistant uudelleen.
5. Asetukset → Laitteet ja palvelut → Lisää integraatio → **Panasonic Comfort Cloud Reliable**.
6. Kirjaudu Panasonic-tilillesi Home Assistantin omassa lomakkeessa. Jos kirjautuminen pyytää vahvistuskoodin, anna se seuraavassa vaiheessa. Salasanaa ja kertakäyttökoodia ei tallenneta; päivitystoken tallennetaan Home Assistantin yksityiseen tallennukseen.

Manuaalinen vaihtoehto: kopioi paketin `custom_components/panasonic_cc_reliable` kokonaisuudessaan `/config/custom_components/`-kansioon. Käynnistä uudelleen ja lisää integraatio yllä kuvatulla tavalla.

## Aloita seurannalla

Oletuksena ohjaukset ovat pois käytöstä. Ilmalämpöpumpun ohjauksen saa myöhemmin integraation asetuksista. Aquarea ja erillinen käyttövesipumppu ovat tässä versiossa vain lukutilassa.

Laita vanhan Comfort Cloud -integraation kyselyt pois päältä testin ajaksi. Näin samalle tilille ei tule kahden integraation kyselyjä. Uusi komponentti ei korvaa vanhan komponentin tiedostoja, sillä integraation tunniste on eri.

Sopivat alkuasetukset:

- Päivitysväli 120 s.
- Tiedon enimmäisikä 600 s.
- Energiahistoria pois käytöstä, kunnes tavallinen seuranta toimii.
- Raakamittarit pois käytöstä, ellei lisädataa tutkita.

## Mitä lisädataa voidaan löytää?

**Luo ylimääräiset raakamittarit** -asetus etsii laitevastauksen numerokentät. Entiteetit ovat aluksi pois käytöstä ja löytyvät entiteettilistalta. Kentän nimi ei yksin vahvista merkitystä, yksikköä tai skaalaa. Esimerkiksi kompressorin kierroksia tai COP-arvoa ei tässä versiossa oleteta olevan saatavilla.

Integraation valikosta voi ladata diagnostiikan, jossa näkyvät laitelistan ja tilavastauksen kentät. Tunnistetut tilin ja laitteen yksilöivät tiedot peitetään. Tarkista tiedosto ennen jakamista. Lisämittarit voidaan tehdä todellisten vastausten ja laitteen sovelluksen vertailun perusteella.

## Yhteyden tilan tulkitseminen

| Tila | Merkitys |
| --- | --- |
| `connected` | Tiedot saatiin onnistuneesti laitteen live-rajapinnasta tai käyttövesilaitteen ryhmälistasta. Tämä ei takaa, että laitteen sisäinen mittaus on juuri nyt tehty. |
| `degraded` | Viime arvo säilyy lyhyen häiriön ajan tai tieto tuli välimuistista. |
| `stale` | Tieto on liian vanhaa tai välimuistivastauksen ikää ei voi varmistaa. Varsinaiset mittarit merkitään unavailable-tilaan. |
| `account_degraded` | Tilin pilviyhteydessä tai kyselyrajoissa on häiriö. |
| `account_error` | Koko tilin päivitys epäonnistui. |
| `removed` | Laite ei enää näy tilin laitelistassa. |

**Last successful fetch** kertoo, milloin HA sai vastauksen. **Cloud timestamp** on erikseen Panasonicin palauttama aikaleima; sen tarkkaa merkitystä ei ole vahvistettu. Välimuistin tieto ei oikeuta ohjauskäskyihin.

Jos kirjautuminen vanhenee, Home Assistant pyytää uudelleenkirjautumista. Integraatiota ei tarvitse poistaa. Päivitetyt käyttöehdot hyväksytään itse Panasonicin virallisessa sovelluksessa.

## Päivitys 0.1.1

Versio lisää pystysuuntaisen ja vaakasuuntaisen swing-valinnan climate-entiteettiin, käyttötilan, puhallinasetuksen, quiet/powerful-tilan ja päälläolon. Energia-asetuksen ollessa päällä syntyvät päiväkulutus sekä pilven palauttamien kelvollisten osuuksien perusteella lämmitys- ja jäähdytyssähkön päiväkulutus. Ohjaus ja energiahaku otetaan käyttöön integraation asetuksista. Päiväkulutus on Panasonicin pilviarvo; lämpötehoa tai COP-arvoa ei lasketa siitä.

## Integraation kuvake

Paketissa on Panasonic Comfort Cloud -kuvake koossa 256 × 256 ja 512 × 512.
Kopioi myös komponentin `brand`-kansio päivityksessä. Home Assistant 2026.10.1
tukee näiden paikallisten kuvakkeiden näyttämistä integraation kortissa.

Jos haluat lisätä vain kuvakkeen olemassa olevaan asennukseen, kopioi
[ICON_INSTALL.sh](ICON_INSTALL.sh) Terminal & SSH -lisäosaan ja suorita se.
Skripti lataa kuvakkeet ja niiden lisenssin Socklessin julkisen GitHub-repon
yksilöidystä versiosta sekä käynnistää Home Assistantin uudelleen.
Päivitä sivu tai avaa Home Assistant -sovellus uudelleen käynnistyksen jälkeen.
