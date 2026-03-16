
## **SHORT:** 
**Potential Solution Size:** 10 million dollars, **Solution:** Coaching and Game Solver Software, **Technical:** GPT and Neural Network, **Users Market:** 600,000 current bridge players, **Specialized Expertise:** Developers are nationally competitive bridge players.

## **Current issue:** 
Contract Bridge is a strategy-based card game in which players bid for a contract. The game, however, suffers from a steep learning curve and can only be played in groups of four. This means the game is particularly hard to learn or improve at unless you have a group of four players at the same level and with the same passion.

## **Solution:** 
Our product is a Bridge-Coach model that plays against players, learns strategy, and coaches them on their play using GPT.

## **Users**
 Our potential users are bridge players with skill levels ranging from interested to advanced.

## **Differences from the market:** 
No bridge-coaching software is currently available that provides feedback to the player, and the current top bridge-playing software is a neural network that does not take into account information about the individual player with whom it is playing. They act simply as if they are playing against another AI that plays the same way. This is a major issue, as playing with a partner who shares the same strategy is core to success in the game. As our software will be able to read a player's convention card (Mandated Strategy Declaration), it will be able to adapt to its partner and coach according to the strategy of the opponents. By using AI instead of simple heuristics, it can leverage the many strategies that are core to partnership gameplay in contract bridge.

## **Market Size:** 
The game is still popular today, with the World Bridge Federation having over 530,000 affiliated members. Bridge Base, one of the popular Bridge websites, has around 14,000 active players. Based on these and other organizations, we estimate a client base of around 600,000. Bridge Base Online has an estimated net revenue of 7.5 Million Dollars through robot partner games. Therefore, using the numbers from Bridge Base and other online providers, we conservatively estimate the potential market of 10 million for GEKO. 

## **Technical:** 
The game consists of two distinct phases: the bidding phase and the card play phase. Therefore, similarly, we break the bridge solver into two distinct parts. 
Bidding Model Solver: The Input: the Convention Card of other Players, Bidding History, Bidding Model Outputs, Best possible next bid. Training will be done by using a latent learning model. 

- **Card play Model Solver:** Input Convention Card of Human Player, Bidding History, Double Dummy, Card playing History. Output: best possible next move. This will be trained by trying to maximize the card play outcome compared to double dummy, a best-possible-outcome solver that uses branching and full information to determine the best possible next play. 

- **The Coaching Software:** This will operate similarly, taking in all the same information as the playing or bidding model and the outputs from that phase. This will be trained using the bridge literature. 

- **Development:** Double dummy will train card play; Card play will train the bidding model; the bidding model and Double dummy will then train Card play; Card Play model will, in turn, serve as training input to the Bidding model. The coaching model will be trained on the bridge literature.

## **Minimum viable product outcomes:** 
- A user can bid, and our system returns a near-expert response. 
- A user can make a play, and our system returns a near-expert response. 
- A user can make a mistake, and our system returns feedback on that response

## **Top sources of information:** 
Bridge Webs and Bridge Bum for bidding and playing to text, Bridge Base for played hands, and Double Dummy for card play development.

## **Risks:** 
Limited availability of information, Limited Access to clients, and compounding training could lead to overfitting.
## **View More**
**Working Document with Devlopment Plan and Reaserch**
>https://docs.google.com/document/d/1xZoK_cYJ6gdN7i4bWNUwEGE84FgnHGcAbojvDdZYgJM/edit?usp=sharing

**Video**
>https://youtu.be/ehbxypiX-_Y
