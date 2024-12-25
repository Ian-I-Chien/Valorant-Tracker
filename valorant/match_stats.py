class MatchStats:
    def __init__(self):
        self.highest_ratio = -1
        self.total_head = 0
        self.total_shots = 0
        self.total_kda = 0
        self.highest_kills = -1
        self.lowest_ratio = int(1e9)
        self.total_matches = 0
        self.total_wins = 0

    def update_stats(self, match):
        player_team = match["stats"]["team"]
        red_score = match["teams"]["red"]
        blue_score = match["teams"]["blue"]
        kills = match["stats"]["kills"]
        deaths = match["stats"]["deaths"]
        assists = match["stats"]["assists"]
        shots = match["stats"]["shots"]
        head = shots["head"]
        body = shots["body"]
        leg = shots["leg"]

        total_shots_in_match = head + body + leg

        if deaths > 0:
            match_kda = (kills + assists) / deaths
        else:
            match_kda = kills + assists

        self.total_kda += match_kda
        self.total_matches += 1

        self.highest_kills = max(self.highest_kills, kills)

        self.total_head += head
        self.total_shots += total_shots_in_match
        if total_shots_in_match > 0:
            headshot_ratio_each_match = (head / total_shots_in_match) * 100
            self.highest_ratio = max(self.highest_ratio, headshot_ratio_each_match)
            self.lowest_ratio = min(self.lowest_ratio, headshot_ratio_each_match)

        if player_team == "Red" and red_score > blue_score:
            self.total_wins += 1
        elif player_team == "Blue" and blue_score > red_score:
            self.total_wins += 1

    def get_summary(self):
        if self.total_shots > 0:
            average_headshot_ratio = (self.total_head / self.total_shots) * 100
            average_kda = self.total_kda / self.total_matches
            win_rate = (self.total_wins / self.total_matches) * 100
            return (
                round(average_headshot_ratio, 2),
                round(self.highest_ratio, 2),
                round(self.lowest_ratio, 2),
                self.highest_kills,
                round(average_kda, 2),
                round(win_rate, 2),
            )
        else:
            return None
