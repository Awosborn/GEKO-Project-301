#Data will store all the following data for each game 

#Define StratDec of partner player to use as rules for bidding stage in game loop
#StratDec will be a matrix containing values corresponding to quesitions that are on a convention card
#it will have defined values
#ignore the Strat dec for now

#Curr_Card_Hold this will be an array 4 by 13 with the values meaning which card each user has been given 
#the values will begin at 2 club index of [0,0] followed by 2 of diamonds then hearts then spades the next row will begin with 3 of Clubs [1,0] this patern continues with the order of the face cards being J,Q,K, A till the Ace of spades at [13,4]

#Curr_Bid_Hist this will store the bids that each input made durring bidding stage this will be an array of (however many rows needed) by 4 coloums which correspond to the user 
# the values will be integers starting at 0 = 1 Club followed by 1= 1 Diamond, 2= 1 Heart,3= 1 Spade, 4= 1 No Trump, 5= 2 Club and the patern continus till 7NT

#Curr_Points will store how many points the users got in that round of game loop

#Hist_Points will store how many points the users have in total
