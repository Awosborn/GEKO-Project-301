### The Product:
Our product is a Bridge-Coach model that plays against players, learns strategy, and coaches them on their play using GPT.
### Minimum viable product outcomes: 
A user can bid, and our system returns a near-expert response. 
A user can make a play, and our system returns a near-expert response. 
A user can make a mistake, and our system returns feedback on that response

---
### Current Structure and Progress
The current structure is set up with the capabilities to train our preliminary model, which will be able to both bid and play contract bridge. This current stage of the project is set up with two submodels: latent learning model and a supervised model. 


read.md- includes generic documentation of how to start running program

Run_this.py - entry point to begin

MVP/Data.py - Defines main Bridge objectives data Structures as well as tracking state data

MVP/GameLoop.py - Simulates one round of bridge

MVP/RukesChecker.py -  Checks if everything works under compliance of rules

MVP/training_tokens.json - Embeds the tokens and keeps track of token vocabulary

MVP/bridge_nine_strategy_profiles.json- has the current used strategy declaration 

Current Succsess
-Manage to get 2 gigabytes worth of data from past online bridge games
-converted to a JSON file that is usable data
-successfully integrable with training set

---
### Current Technical Difficulties:
The main challenge we currently face is the training of our model. We have completed a multitude of versions of the code to try to get it to produce reasonable outputs (correct predictions of bridge bids), but there is a convergence issue. Once we get one model to perform reasonably we can start iterating and training the models on its previous versions

---
### Steps to Complete
Run the training for Model 1 on all of the training data
Use the Latent Learning model to train multiple versions of the project on itself
Make the ChatGPT wrapper to give feedback to human users based off of predictive model
Make the UI in order to play with people



