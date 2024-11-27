class MatchStats:
    def __init__(self):
        self.highest_ratio = -1
        self.highest_deaths = -1
        self.total_head = 0
        self.total_shots = 0
        self.lowest_kill = int(1e9)
        self.lowest_ratio = int(1e9)

    def update_stats(self, match):
        kills = match["stats"]["kills"]
        deaths = match["stats"]["deaths"]
        shots = match["stats"]["shots"]
        head = shots["head"]
        body = shots["body"]
        leg = shots["leg"]
        
        total_shots_in_match = head + body + leg

        self.lowest_kill = min(self.lowest_kill, kills)
        self.highest_deaths = max(self.highest_deaths, deaths)

        self.total_head += head
        self.total_shots += total_shots_in_match
        if total_shots_in_match > 0:
            headshot_ratio_each_match = (head / total_shots_in_match) * 100
            self.highest_ratio = max(self.highest_ratio, headshot_ratio_each_match)
            self.lowest_ratio = min(self.lowest_ratio, headshot_ratio_each_match)

    def get_summary(self):
        if self.total_shots > 0:
            average_headshot_ratio = (self.total_head / self.total_shots) * 100
            return (
                round(average_headshot_ratio, 2),
                round(self.highest_ratio, 2),
                round(self.lowest_ratio, 2),
                self.highest_deaths,
                self.lowest_kill,
            )
        else:
            return None
