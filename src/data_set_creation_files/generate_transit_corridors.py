import os
import math
import random
import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

OUTPUT_PATH = "data/raw/transit_corridors.parquet"
NUM_RECORDS = 5000

HUBS = [
    {"city": "Bhiwandi/Mumbai", "state": "27", "pin": "421302"},
    {"city": "Bengaluru", "state": "29", "pin": "560058"},
    {"city": "Gurugram/NCR", "state": "06", "pin": "122001"},
    {"city": "Chennai", "state": "33", "pin": "600001"},
    {"city": "Ahmedabad", "state": "24", "pin": "382405"},
    {"city": "Kolkata", "state": "19", "pin": "700001"},
    {"city": "Hyderabad", "state": "36", "pin": "500001"},
    {"city": "Pune", "state": "27", "pin": "411019"},
    {"city": "Jaipur", "state": "08", "pin": "302001"},
    {"city": "Coimbatore", "state": "33", "pin": "641001"},
    {"city": "Nagpur", "state": "27", "pin": "440001"},
    {"city": "Baddi/Himachal", "state": "02", "pin": "173205"}
]

TERRAINS = ["plains", "ghats", "hilly", "mixed"]
SEASONS = ["dry", "monsoon", "winter_fog"]
ROUTE_CATS = ["golden_quadrilateral", "national_corridor", "state_feeder", "hilly_artery"]

def calculate_statutory_validity(distance_km, cargo_type):
    rate = 200.0 if cargo_type == "R" else 20.0
    days = math.ceil(distance_km / rate)
    return max(1, days)

def main():
    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    random.seed(42)
    np.random.seed(42)

    rows = []

    for i in range(NUM_RECORDS):
        corridor_id = f"CORR-{i+1:05d}"
        
        origin = random.choice(HUBS)
        dest = random.choice([h for h in HUBS if h["pin"] != origin["pin"]])
        
        if origin["state"] == dest["state"]:
            distance = round(random.uniform(50.0, 480.0), 1)
        else:
            distance = round(random.uniform(450.0, 2400.0), 1)

        cargo_type = "O" if random.random() < 0.10 else "R"
        
        validity_days = calculate_statutory_validity(distance, cargo_type)
        validity_hours = validity_days * 24.0

        is_mountain = any(h in (origin["city"], dest["city"]) for h in ["Baddi/Himachal", "Pune"])
        terrain = "ghats" if is_mountain and random.random() < 0.70 else random.choice(TERRAINS)
        season = random.choice(SEASONS)
        route_cat = "golden_quadrilateral" if distance > 900 else random.choice(ROUTE_CATS)

        if cargo_type == "O":
            base_speed = random.uniform(7.0, 12.0)
        else:
            if terrain == "plains":
                base_speed = random.uniform(32.0, 44.0)
            elif terrain == "mixed":
                base_speed = random.uniform(24.0, 34.0)
            else:
                base_speed = random.uniform(16.0, 26.0)

        toll_count = max(1, int(distance / 65.0))
        toll_delay = toll_count * random.uniform(0.25, 0.50)

        weather_penalty = 1.0
        if season == "monsoon":
            weather_penalty = random.uniform(1.20, 1.45)
        elif season == "winter_fog" and any(origin["state"] in ["06", "08", "02"] or dest["state"] in ["06", "08", "02"] for _ in [1]):
            weather_penalty = random.uniform(1.30, 1.65)

        driving_hours = (distance / base_speed) * weather_penalty
        
        # mandatory rest stops and driver shift changes
        driver_rest_hours = (driving_hours / 10.0) * random.uniform(6.0, 10.0)

        # realistic freight frictions: loading bay congestion, mechanical fault, or highway check
        incident_roll = random.random()
        if incident_roll < 0.18:
            incident_delay = random.uniform(18.0, 36.0)
        elif incident_roll < 0.35:
            incident_delay = random.uniform(8.0, 16.0)
        else:
            incident_delay = 0.0

        actual_transit_hours = round(driving_hours + toll_delay + driver_rest_hours + incident_delay, 2)
        variance_hours = round(actual_transit_hours - validity_hours, 2)
        
        is_overrun = 1 if actual_transit_hours > validity_hours else 0

        rows.append({
            "corridor_id": corridor_id,
            "origin_pin": origin["pin"],
            "destination_pin": dest["pin"],
            "origin_state": origin["state"],
            "destination_state": dest["state"],
            "route_category": route_cat,
            "terrain_type": terrain,
            "distance_km": distance,
            "cargo_type": cargo_type,
            "statutory_validity_days": validity_days,
            "statutory_validity_hours": validity_hours,
            "base_speed_kmh": round(base_speed, 2),
            "toll_checkpoints_count": toll_count,
            "checkpoint_delay_hours": round(toll_delay, 2),
            "season": season,
            "actual_transit_hours": actual_transit_hours,
            "hours_delay_variance": variance_hours,
            "is_expired_overrun": is_overrun
        })

    df = pd.DataFrame(rows)

    schema = pa.schema([
        ("corridor_id", pa.string()),
        ("origin_pin", pa.string()),
        ("destination_pin", pa.string()),
        ("origin_state", pa.string()),
        ("destination_state", pa.string()),
        ("route_category", pa.string()),
        ("terrain_type", pa.string()),
        ("distance_km", pa.float64()),
        ("cargo_type", pa.string()),
        ("statutory_validity_days", pa.int64()),
        ("statutory_validity_hours", pa.float64()),
        ("base_speed_kmh", pa.float64()),
        ("toll_checkpoints_count", pa.int64()),
        ("checkpoint_delay_hours", pa.float64()),
        ("season", pa.string()),
        ("actual_transit_hours", pa.float64()),
        ("hours_delay_variance", pa.float64()),
        ("is_expired_overrun", pa.int64())
    ])

    table = pa.Table.from_pandas(df, schema=schema)
    pq.write_table(table, OUTPUT_PATH, compression="snappy")

    print(f"successfully built {len(df)} transit corridor records in {OUTPUT_PATH}")
    print("recalibrated overrun distribution:")
    print(df["is_expired_overrun"].value_counts(normalize=True))

if __name__ == "__main__":
    main()