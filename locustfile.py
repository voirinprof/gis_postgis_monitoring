from locust import HttpUser, task, between
import random

# pool of addresses to simulate user input
addresses = [
    "485 ROUTE DE WINDSOR",    
    "3747 RUE DUNANT",
    "3135 RUE DES ARTISANS",
    "2955 BOULEVARD DE L'UNIVERSITE",
    "2745 RUE DE LA SHERWOOD",
    "135 RUE DON BOSCO N",
    "3400 BOULEVARD DE PORTLAND",
    "2875 RUE DU MANOIR",
    "3110 CHEMIN DES ECOSSAIS",
    "35 RUE DU CURE LAROCQUE",
    "160 RUE RENE",
    "156 RUE CLARK",
    "611 RUE POULIN",
    "2160 RUE DES CERISIERS",
    "2625 RUE DES CYPRES",
    "1191 RUE LAROCQUE",
    "25 RUE BELVEDERE N",
    "127 RUE MORRIS",
    "475 RUE IRENE COUTURE",
    "330 RUE RODOLPHE RACINE",
    "436 CHEMIN GODIN",
    "153 RUE DES COLIBRIS",
    "425 RUE SAINT MICHEL",
    "528 RUE LAURIER"
]


class FlaskAppUser(HttpUser):
    # wait_time = between(1, 5)
    wait_time = between(1, 5)
    
    # URL of the Flask app
    host = "http://localhost:5000"
    
    @task(2)  # weights of 2 for the task
    def get_home(self):
        response = self.client.get("/")
        if response.status_code != 200:
            response.failure(f"GET / failed with status {response.status_code}")
    
    @task(1)  # weights of 1 for the task
    def findpath(self):
        # Generate random coordinates to simulate varied data
        start = random.choices(addresses)
        end = random.choice(addresses)
        
        response = self.client.get("/findpath", params={"start": start, "end": end})
                
        if response.status_code != 200:
            response.failure(f"GET /findpath failed with status {response.status_code}")