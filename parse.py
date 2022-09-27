import argparse
import requests
from steam import webapi as steam_webapi
from steam.steamid import SteamID
from enum import Enum

STRATZ_API = 'https://api.stratz.com/graphql'
STRATZ_TOKEN = None
STEAM_TOKEN = None

class Medal(Enum):
    UNRANKED = 0
    HERALD=1
    GUARDIAN=2
    CRUSADER=3
    ARCHON=4
    LEGEND=5
    ANCIENT=6
    DIVINE=7
    IMMORTAL=8

    @classmethod
    def from_int(cls, value):
        if value == None:
            return cls(0)
        return cls(value // 10)

class RankMedal:
    def __init__(self, num):
        self.medal = Medal.from_int(num)
        self.stars = num % 10 if num != None else None

    def __str__(self):
        return '{}{}'.format(self.medal.name.title(), '[{}]'.format(self.stars) if self.stars else '')

class Json2Obj:
    def __init__(self, data):
        self.__dict__ = data
        for i in self.__dict__.keys():
            child = self.__dict__[i]
            if isinstance(child, dict):
                if len(child) > 0:
                    self.__dict__[i] = Json2Obj(child)
            if isinstance(child, list):
                self.__dict__[i] = []
                for item in child:
                    if isinstance(item, dict):
                        self.__dict__[i].append(Json2Obj(item))
                    else:
                        self.__dict__[i].append(item)

class BearerAuth(requests.auth.AuthBase):
    def __init__(self, token):
        self.token = token

    def __call__(self, r):
        r.headers["authorization"] = "Bearer " + self.token
        return r

class Profile:
    def __init__(self, account_id):
        self.steamID = SteamID(account_id)
        self.stratz_data = None
        self.steam_data = None
        self._n_friends = -1
        self.fetch()

    @property
    def rank(self) -> RankMedal:
        return RankMedal(self.stratz_data.steamAccount.seasonRank)

    @property
    def medal(self) -> Medal:
        self.rank.medal

    @property
    def medal_stars(self) -> int:
        return self.rank.stars

    @property
    def rank_int(self) -> int:
        return self.stratz_data.steamAccount.seasonRank

    @property
    def played(self) -> int:
        return self.stratz_data.matchCount

    @property
    def winrate(self) -> float:
        return self.stratz_data.winCount / self.stratz_data.matchCount

    @property
    def dota_anonymous(self) -> bool:
        return self.stratz_data.steamAccount.isAnonymous

    @property
    def dota_level(self) -> int:
        return self.stratz_data.steamAccount.dotaAccountLevel

    @property
    def steam_anonymous(self) -> bool:
        """
        This represents whether the profile is visible or not, and if it is visible, why you are allowed to see it.
        Note that because this WebAPI does not use authentication, there are only two possible values returned:
        1 - the profile is not visible to you (Private, Friends Only, etc),
        3 - the profile is "Public", and the data is visible.
        Mike Blaszczak's post on Steam forums says,
        "The community visibility state this API returns is different than the privacy state.
        It's the effective visibility state from the account making the request to the account
        being viewed given the requesting account's relationship to the viewed account."
        """

        return self.stratz_data.steamAccount.communityVisibleState != 3

    @property
    def stratz_anmymous(self) -> bool:
        return self.stratz_data.steamAccount.isStratzAnonymous

    @property
    def stratz_smurf(self) -> bool:
        return self.stratz_data.steamAccount.smurfFlag == 1

    @property
    def steam_profile_set_up(self) -> bool:
        return self.steam_data.profilestate == 1

    @property
    def n_friends(self) -> bool:
        if self._n_friends == -1:
            if not self.steam_anonymous:
                data = steam_webapi.get(
                    interface='ISteamUser',
                    method='GetFriendList',
                    version=1,
                    params={
                        'key': STEAM_TOKEN,
                        'steamid': self.steamID.as_64,
                        'relationship': 'friend'
                    }
                )
                self._n_friends = len(data['friendslist']['friends'])
            self._n_friends = None
        return self._n_friends

    def flags(self):
        flags = [
            'rank',
            'played',
            'winrate',
            'dota_anonymous',
            'dota_level',
            'steam_anonymous',
            'stratz_anmymous',
            'stratz_smurf',
            'steam_profile_set_up',
            'n_friends',
        ]
        flags_dict = {flag: getattr(self, flag) for flag in flags}
        return flags_dict

    def _fetch_stratz(self):
        query = (
            "{\n"
            "   player(steamAccountId: %s) {\n"
            "       firstMatchDate\n"
            "       lastMatchDate\n"
            "       matchCount\n"
            "       names {\n"
            "           name\n"
            "           lastSeenDateTime\n"
            "       }\n"
            "       steamAccount {\n"
            "           avatar\n"
            "           isAnonymous\n"
            "           isDotaPlusSubscriber\n"
            "           isStratzAnonymous\n"
            "           name\n"
            "           seasonRank\n"
            "           smurfFlag\n"
            "           timeCreated\n"
            "           dotaAccountLevel\n"
            "           communityVisibleState\n"
            "           battlepass {\n"
            "               eventId\n"
            "               level\n"
            "           }\n"
            "           profileUri\n"
            "       }\n"
            "       steamAccountId\n"
            "       winCount\n"
            "       ranks {\n"
            "           asOfDateTime\n"
            "           rank\n"
            "           seasonRankId\n"
            "       }\n"
            "   }\n"
            "}\n"
        ) % (
            self.steamID.id
        )
        response = requests.post(
            STRATZ_API, json={'query': query}, auth=BearerAuth(STRATZ_TOKEN))
        try:
            self.stratz_data = Json2Obj(response.json()['data']['player'])
        except Exception as e:
            print(e)
            raise e

    def _fetch_steam(self):
        data = steam_webapi.get(
            interface='ISteamUser',
            method='GetPlayerSummaries',
            version=2,
            #key=STEAM_TOKEN,
            params={
                'key': STEAM_TOKEN,
                'steamids':self.steamID.as_64
            }
        )

        self.steam_data = Json2Obj(data['response']['players'][0])

    def fetch(self):
        self._fetch_stratz()
        self._fetch_steam()

if __name__ == '__main__':
    # Argument parser
    parser = argparse.ArgumentParser(description='Detect elements in images')
    parser.add_argument('-s', '--stratz_token', required=True,
                        type=str, help='Stratz API token')
    parser.add_argument('-v', '--valve_token', required=True, type=str,
                        help='Valve API token')

    # parse known argguments
    args, unknown = parser.parse_known_args()
    STRATZ_TOKEN = args.stratz_token
    STEAM_TOKEN = args.valve_token

    players = [
        Profile(95251565),  # me
        Profile(89428432),  # P[A]conar
        Profile(1252911151), #some smurf
    ]

    for p in players:
        print(p.stratz_data.steamAccount.name, '|'.join([f'{k}:{v}' for k, v in p.flags().items()]))

    #p1_matches = get_matches(95251565)
    #p2_matches = get_matches(89428432)
    pass
