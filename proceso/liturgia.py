#!/usr/bin/env python3
"""CatholicAid · Calendario litúrgico (rito romano, calendario general).

- pascua(año), tiempo_liturgico(fecha): adviento / navidad / cuaresma / pascua / ordinario.
- dia_liturgico(fecha, idioma): nombre del día SOLO cuando es seguro (domingos y fiestas grandes): «Domingo XXXIII
  del Tiempo Ordinario», «Jesucristo, Rey del Universo», «Miércoles de Ceniza»… Si hay duda (fiestas que unos países
  celebran en jueves y otros en domingo: Ascensión, Corpus; solemnidades trasladadas), devuelve "": mejor callar
  que poner un nombre equivocado.
- dias_para_navidad(fecha): para la cuenta atrás de Adviento.
"""
import datetime as dt

ROMANOS = ["", "I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII", "XIII", "XIV", "XV", "XVI",
           "XVII", "XVIII", "XIX", "XX", "XXI", "XXII", "XXIII", "XXIV", "XXV", "XXVI", "XXVII", "XXVIII", "XXIX",
           "XXX", "XXXI", "XXXII", "XXXIII", "XXXIV"]
ORDINALES_EN = ["", "First", "Second", "Third", "Fourth", "Fifth", "Sixth", "Seventh"]

# Color de acento por tiempo (RGB hex): morado suave en Adviento y Cuaresma; dorado el resto del año.
COLOR = {"adviento": "C9A6F0", "cuaresma": "C9A6F0"}
COLOR_NORMAL = "F5C542"
NOMBRE_TIEMPO = {"adviento": {"es": "Adviento", "en": "Advent", "pt": "Advento"},
                 "cuaresma": {"es": "Cuaresma", "en": "Lent", "pt": "Quaresma"}}

# Fiestas de fecha fija que se nombran si NO caen en domingo ni cerca de la Pascua (ahí pueden trasladarse).
FIJAS = {
    (1, 1): ("Santa María, Madre de Dios", "Mary, the Holy Mother of God", "Santa Maria, Mãe de Deus"),
    (1, 6): ("Epifanía del Señor", "The Epiphany of the Lord", "Epifania do Senhor"),
    (2, 2): ("Presentación del Señor", "The Presentation of the Lord", "Apresentação do Senhor"),
    (3, 19): ("San José, esposo de la Virgen María", "Saint Joseph, Spouse of the Blessed Virgin Mary",
              "São José, esposo da Virgem Maria"),
    (3, 25): ("Anunciación del Señor", "The Annunciation of the Lord", "Anunciação do Senhor"),
    (6, 24): ("Natividad de san Juan Bautista", "The Nativity of Saint John the Baptist",
              "Natividade de São João Batista"),
    (6, 29): ("San Pedro y san Pablo, apóstoles", "Saints Peter and Paul, Apostles", "São Pedro e São Paulo, apóstolos"),
    (8, 6): ("Transfiguración del Señor", "The Transfiguration of the Lord", "Transfiguração do Senhor"),
    (8, 15): ("Asunción de la Virgen María", "The Assumption of the Blessed Virgin Mary",
              "Assunção de Nossa Senhora"),
    (9, 14): ("Exaltación de la Santa Cruz", "The Exaltation of the Holy Cross", "Exaltação da Santa Cruz"),
    (11, 1): ("Todos los Santos", "All Saints", "Todos os Santos"),
    (11, 2): ("Conmemoración de todos los fieles difuntos", "The Commemoration of All the Faithful Departed",
              "Comemoração de todos os fiéis defuntos"),
    (12, 8): ("Inmaculada Concepción de la Virgen María", "The Immaculate Conception of the Blessed Virgin Mary",
              "Imaculada Conceição de Nossa Senhora"),
    (12, 25): ("Natividad del Señor", "The Nativity of the Lord", "Natal do Senhor"),
}
I = {"es": 0, "en": 1, "pt": 2}


def pascua(anio):
    """Domingo de Pascua (calendario gregoriano, algoritmo de Meeus/Jones/Butcher)."""
    a, b, c = anio % 19, anio // 100, anio % 100
    d, e = b // 4, b % 4
    g = (8 * b + 13) // 25
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 19 * l) // 433
    mes = (h + l - 7 * m + 90) // 25
    return dt.date(anio, mes, (h + l - 7 * m + 33 * mes + 19) % 32)


def inicio_adviento(anio):
    """Primer domingo de Adviento: el cuarto domingo antes de Navidad."""
    navidad = dt.date(anio, 12, 25)
    return navidad - dt.timedelta(days=(navidad.isoweekday() % 7 or 7) + 21)


def bautismo(anio):
    """Bautismo del Señor: el domingo siguiente al 6 de enero."""
    epifania = dt.date(anio, 1, 6)
    return epifania + dt.timedelta(days=7 - epifania.isoweekday() % 7)


def tiempo_liturgico(fecha):
    """adviento / navidad / cuaresma / pascua / ordinario (rito romano, Epifanía el 6 de enero)."""
    navidad = dt.date(fecha.year, 12, 25)
    if inicio_adviento(fecha.year) <= fecha < navidad:
        return "adviento"
    if fecha >= navidad or fecha <= bautismo(fecha.year):
        return "navidad"
    p = pascua(fecha.year)
    if p - dt.timedelta(days=46) <= fecha < p:
        return "cuaresma"
    if p <= fecha <= p + dt.timedelta(days=49):  # hasta Pentecostés
        return "pascua"
    return "ordinario"


def color_tiempo(fecha):
    return COLOR.get(tiempo_liturgico(fecha), COLOR_NORMAL)


def etiqueta_tiempo(fecha, idioma="es"):
    """«Adviento» / «Cuaresma» en el idioma del vídeo, o "" el resto del año."""
    return NOMBRE_TIEMPO.get(tiempo_liturgico(fecha), {}).get(idioma, "")


def dias_para_navidad(fecha):
    """Días que faltan para el 25 de diciembre, solo en Adviento (si no, None)."""
    if tiempo_liturgico(fecha) != "adviento":
        return None
    return (dt.date(fecha.year, 12, 25) - fecha).days


def _domingo(n, tiempo, idioma):
    if idioma == "en":
        if tiempo == "ordinario":
            sufijo = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
            return f"{n}{sufijo} Sunday in Ordinary Time"
        return f"{ORDINALES_EN[n]} Sunday of " + {"adviento": "Advent", "cuaresma": "Lent", "pascua": "Easter"}[tiempo]
    if idioma == "pt":
        return f"{n}º Domingo " + {"adviento": "do Advento", "cuaresma": "da Quaresma", "pascua": "da Páscoa",
                                   "ordinario": "do Tempo Comum"}[tiempo]
    return f"Domingo {ROMANOS[n]} " + {"adviento": "de Adviento", "cuaresma": "de Cuaresma", "pascua": "de Pascua",
                                       "ordinario": "del Tiempo Ordinario"}[tiempo]


def dia_liturgico(fecha, idioma="es"):
    """Nombre del día litúrgico cuando es seguro; "" si es un día corriente o hay duda."""
    k = I.get(idioma, 0)
    p = pascua(fecha.year)
    moviles = {
        p - dt.timedelta(days=46): ("Miércoles de Ceniza", "Ash Wednesday", "Quarta-feira de Cinzas"),
        p - dt.timedelta(days=7): ("Domingo de Ramos en la Pasión del Señor", "Palm Sunday of the Passion of the Lord",
                                   "Domingo de Ramos da Paixão do Senhor"),
        p - dt.timedelta(days=3): ("Jueves Santo", "Holy Thursday", "Quinta-feira Santa"),
        p - dt.timedelta(days=2): ("Viernes Santo", "Good Friday", "Sexta-feira Santa"),
        p: ("Domingo de Pascua de la Resurrección del Señor", "Easter Sunday of the Resurrection of the Lord",
            "Domingo de Páscoa da Ressurreição do Senhor"),
        p + dt.timedelta(days=49): ("Domingo de Pentecostés", "Pentecost Sunday", "Domingo de Pentecostes"),
        p + dt.timedelta(days=56): ("Santísima Trinidad", "The Most Holy Trinity", "Santíssima Trindade"),
        inicio_adviento(fecha.year) - dt.timedelta(days=7): (
            "Jesucristo, Rey del Universo", "Our Lord Jesus Christ, King of the Universe",
            "Nosso Senhor Jesus Cristo, Rei do Universo"),
        bautismo(fecha.year): ("Bautismo del Señor", "The Baptism of the Lord", "Batismo do Senhor"),
    }
    if fecha in moviles:
        return moviles[fecha][k]
    # Días que cada país celebra en fecha distinta (Ascensión, Corpus) o con lecturas propias: no se nombran.
    dudosos = {p + dt.timedelta(days=d) for d in (39, 42, 60, 63)}
    semana_santa_y_octava = p - dt.timedelta(days=7) <= fecha <= p + dt.timedelta(days=7)
    domingo = fecha.isoweekday() == 7
    if fecha in dudosos:
        return ""
    fija = FIJAS.get((fecha.month, fecha.day))
    if fija and not semana_santa_y_octava and (not domingo or (fecha.month, fecha.day) == (12, 25)):
        return fija[k]
    if not domingo or fija:  # una fiesta fija en domingo puede ganarle al domingo o trasladarse: no se nombra
        return ""
    tiempo = tiempo_liturgico(fecha)
    if tiempo == "adviento":
        return _domingo((fecha - inicio_adviento(fecha.year)).days // 7 + 1, tiempo, idioma)
    if tiempo == "cuaresma":
        return _domingo((fecha - (p - dt.timedelta(days=42))).days // 7 + 1, tiempo, idioma)
    if tiempo == "pascua":
        return _domingo((fecha - p).days // 7 + 1, tiempo, idioma)
    if tiempo == "navidad":
        if fecha.month == 12 and 26 <= fecha.day <= 31:
            return ("Sagrada Familia: Jesús, María y José", "The Holy Family of Jesus, Mary and Joseph",
                    "Sagrada Família: Jesus, Maria e José")[k]
        return ""
    if fecha < p:  # tiempo ordinario antes de la Cuaresma: el domingo siguiente al Bautismo es el II
        n = (fecha - bautismo(fecha.year)).days // 7 + 1
    else:  # después de Pentecostés se cuenta hacia atrás: el domingo anterior al Adviento es el XXXIV
        n = 35 - (inicio_adviento(fecha.year) - fecha).days // 7
    return _domingo(n, tiempo, idioma) if 2 <= n <= 33 else ""
