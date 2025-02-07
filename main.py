import json
import logging
import os
import signal
import random
import fastapi
import requests
import uvicorn
from fastapi import FastAPI
from pydantic import BaseModel
# import pytest

"""
By Javidan Aghayev
Written for Hardin-Simmons CSCI-4332 Artificial Intelligence
Revision History
1.0 - API setup
1.1 - Very basic test player
1.2 - Bugs fixed and player improved, should no longer forfeit
"""


def is_valid_move(move):
    """Check if a move (card) is valid."""
    # Implement any specific validation for moves (e.g., checking for sets or runs)
    return True  # Placeholder, you can add more complex rules later.


class GameState:
    def __init__(self):
        self.hand = []  # List to store cards in the player's hand
        self.discard_pile = []  # List to store discarded cards
        self.stock = []  # List to store cards in the stockpile
        self.is_game_over = False  # To track if the game is over

    def draw_card(self, source):
        """Draw a card from the stock or discard pile."""
        if source == "stock" and self.stock:
            card = self.stock.pop()
        elif source == "discard" and self.discard_pile:
            card = self.discard_pile.pop()
        else:
            return None
        self.hand.append(card)
        return card

    def discard_card(self, card):
        """Discard a card from the player's hand."""
        if card in self.hand:
            self.hand.remove(card)
            self.discard_pile.append(card)
            return card
        return None

    def get_game_state(self):
        """Return the current state of the game."""
        return {
            "hand": self.hand,
            "discard_pile": self.discard_pile,
            "stock_size": len(self.stock),
            "is_game_over": self.is_game_over,
        }

app = FastAPI()

# Initialize GameState
game_state = GameState()

# Create a mock deck (for the stock)
def init_deck():
    return [f"Card {i}" for i in range(1, 53)]  # Simple deck from 1 to 52

# Initialize the stock when the game starts
game_state.stock = init_deck()
random.shuffle(game_state.stock)

class DrawRequest(BaseModel):
    source: str  # Can be "stock" or "discard"

class DiscardRequest(BaseModel):
    card: str


@app.post("/discard")
async def discard(request: DiscardRequest):
    card = game_state.discard_card(request.card)
    if card:
        return {"message": f"Discarded card: {card}"}
    return {"message": "Card not in hand."}

@app.get("/game_state")
async def get_game_state():
    return game_state.get_game_state()

@app.post("/end_game")
async def end_game():
    game_state.is_game_over = True
    return {"message": "Game over."}

DEBUG = True
PORT = 10001
USER_NAME = "crustacean_cheapskate"

# TODO - change your method of saving information from the very rudimentary method here
hand = [] # list of cards in our hand
cannot_discard = ""


# set up the API endpoints
@app.get("/")
async def root():
    """ Root API simply confirms API is up and running."""
    return {"status": "Running"}

# data class used to receive data from API POST
class GameInfo(BaseModel):
    game_id: str
    opponent: str
    hand: str


@app.post("/start-2p-game/")
async def start_game(game_info: GameInfo):
    """ Game Server calls this endpoint to inform player a new game is starting. """
    global hand
    global discard

    # Save the initial hand from the game info
    hand = game_info.hand.split(" ")
    hand.sort()

    # Log the hand
    logging.info("2p game started, hand is "+str(hand))

    # Save the game state to a file
    game_state = {
        "hand": hand,
        "discard": discard
    }
    with open("game_state.json", "w") as f:
        json.dump(game_state, f)

    return {"status": "OK"}

# data class used to receive data from API POST
class HandInfo(BaseModel):
    hand: str

@app.post("/start-2p-hand/")
async def start_hand(hand_info: HandInfo):
    """ Game Server calls this endpoint to inform player a new hand is starting, continuing the previous game. """
    global hand
    global discard
    discard = []

    # Update the hand from the incoming data
    hand = hand_info.hand.split(" ")
    hand.sort()

    # Log the new hand
    logging.info("2p hand started, hand is " + str(hand))

    # Save the updated game state
    game_state = {
        "hand": hand,
        "discard": discard
    }
    with open("game_state.json", "w") as f:
        json.dump(game_state, f)

    return {"status": "OK"}

def process_events(event_text):
    """ Shared function to process event text from various API endpoints """
    # TODO - Your code here. Everything from here to end of function
    global hand
    global discard
    for event_line in event_text.splitlines():

        if (USER_NAME + " draws") in event_line or (USER_NAME + " takes") in event_line:
            print("In draw, hand is "+str(hand))
            print("Drew "+event_line.split(" ")[-1])
            hand.append(event_line.split(" ")[-1])
            hand.sort()
            print("Hand is now "+str(hand))
            logging.info("Drew a "+event_line.split(" ")[-1]+", hand is now: "+str(hand))
        if "discards" in event_line:  # add a card to discard pile
            discard.insert(0, event_line.split(" ")[-1])
        if "takes" in event_line: # remove a card from discard pile
            discard.pop(0)
        if " Ends:" in event_line:
            print(event_line)

# data class used to receive data from API POST
class UpdateInfo(BaseModel):
    game_id: str
    event: str

@app.post("/update-2p-game/")
async def update_2p_game(update_info: UpdateInfo):
    """
        Game Server calls this endpoint to update player on game status and other players' moves.
        Typically only called at the end of game.
    """
    global hand
    global discard

    # Process events from the incoming update
    process_events(update_info.event)

    # Save the updated game state
    game_state = {
        "hand": hand,
        "discard": discard
    }
    with open("game_state.json", "w") as f:
        json.dump(game_state, f)

    return {"status": "OK"}

def load_game_state():
    """ Helper function to load game state from a file """
    global hand
    global discard

    try:
        with open("game_state.json", "r") as f:
            game_state = json.load(f)
            hand = game_state.get("hand", [])
            discard = game_state.get("discard", [])
            logging.info(f"Game state loaded: Hand - {hand}, Discard - {discard}")
    except FileNotFoundError:
        logging.warning("Game state file not found, starting with an empty state.")


@app.post("/draw/")
async def draw(update_info: UpdateInfo):
    """Game Server calls this endpoint to start player's turn with a draw from either the discard or stock pile."""
    global cannot_discard
    process_events(update_info.event)
    # If both stock and discard are empty, return an error (game should handle this case)
    if not discard and not stock:
        return {"play": "error", "message": "No cards left to draw"}
    # If discard pile is empty, draw from stock
    if not discard:
        cannot_discard = ""
        return {"play": "draw stock"}

    top_discard = discard[0]  # The top card from the discard pile

    # Check if the top discard card helps form a meld
    if any(top_discard[0] == card[0] for card in hand):  # Matching rank
        cannot_discard = top_discard
        return {"play": "draw discard"}

    return {"play": "draw stock"}  # Otherwise, draw from stock

def get_of_a_kind_count(hand):
    of_a_kind_count = [0, 0, 0, 0]  # how many 1 of a kind, 2 of a kind, etc. in our hand
    last_val = hand[0][0]
    count = 0
    for card in hand[1:]:
        cur_val = card[0]
        if cur_val == last_val:
            count += 1
        else:
            of_a_kind_count[count] += 1
            count = 0
        last_val = cur_val
    of_a_kind_count[count] += 1  # Need to get the last card fully processed
    return of_a_kind_count

def get_count(hand, card):
    count = 0
    for check_card in hand:
        if check_card[0] == card[0]: count += 1
    return count


def validate_discard(hand, discard_card):
    """ Validate that the player can discard the chosen card """
    if discard_card not in hand:
        return False  # Card not in hand
    return True


@app.post("/player-turn/")
async def player_turn(action: str):
    global current_turn
    global hand
    global discard

    if current_turn == "Player 1":
        if action == "discard":
            discard_card = hand.pop()  # Example: Remove a card from hand
            if not validate_discard(hand, discard_card):
                return {"error": "Cannot discard that card"}
            discard.append(discard_card)
        # Other actions like draw, meld...

        current_turn = "Player 2"
    elif current_turn == "Player 2":
        if action == "discard":
            discard_card = hand.pop()  # Example: Remove a card from hand
            if not validate_discard(hand, discard_card):
                return {"error": "Cannot discard that card"}
            discard.append(discard_card)
        # Other actions like draw, meld...

        current_turn = "Player 1"

    # save_game_state()
    return {"status": "OK", "current_turn": current_turn}

def check_end_of_game():
    """ Check if any player has completed their hand (no cards left) """
    if len(hand) == 0:  # Player has no cards left
        return True
    return False

@app.post("/lay-down/")
async def lay_down(update_info: UpdateInfo):
    global hand
    global discard
    global cannot_discard
    process_events(update_info.event)

    melds = get_melds(hand)

    if melds:
        play_string = ""
        cards_to_remove = []

        for meld in melds:
            play_string += "meld "
            for card in meld:
                play_string += str(card) + " "
                cards_to_remove.append(card)

        # Remove melded cards from hand
        for card in cards_to_remove:
            hand.remove(card)

        # Add discard if any cards are left, discard the highest
        if hand:
            discard_card = hand.pop()
            play_string += "discard " + str(discard_card)

        play_string = play_string.strip()  # Remove trailing space
        logging.info("Playing: " + play_string)
        return {"play": play_string}

    else:  # No melds found, just discard the highest card
        if hand:
            discard_card = hand.pop()
            play_string = "discard " + str(discard_card)
            logging.info("Playing: " + play_string)
            return {"play": play_string}
        else:
            return {"play": "error"}  # No cards left to play

    # """ Game Server calls this endpoint to conclude player's turn with melding and/or discard."""
    # # TODO - Your code here - everything from here to end of function
    # global hand
    # global discard
    # global cannot_discard
    # process_events(update_info.event)
    # of_a_kind_count = get_of_a_kind_count(hand)
    # if (of_a_kind_count[0]+(of_a_kind_count[1]*2)) > 1:
    #     print("Need to discard")
    #     # Too many unmeldable cards, need to discard
    #
    #     # If we have a 1 of a kind, discard the highest
    #
    #     if of_a_kind_count[0]>0:
    #         print("Discarding a single card")
    #         logging.info("Discarding a single card")
    #
    #         # edge case - the last card is 1 of a kind
    #         if hand[-1][0] != hand[-2][0]:
    #             logging.info("Discarding " + hand[-1])
    #             return {"play": "discard " + hand.pop()}
    #
    #         for i in range(len(hand)-2,-1, -1):
    #             if i==0:
    #                 logging.info("Discarding "+hand[0])
    #                 return {"play":"discard "+hand.pop(0)}
    #             if hand[i][0] != hand[i-1][0] and hand[i][0] != hand[i+1][0]:
    #                 logging.info("Discarding "+hand[i])
    #                 return {"play":"discard "+hand.pop(i)}
    #
    #     elif of_a_kind_count[1]>=1:
    #         print("Discarding two of a kind, cannot_discard = "+cannot_discard)
    #         for i in range(len(hand)-1,-1, -1):
    #             if hand[i]!=cannot_discard and get_count(hand, hand[i]) == 2:
    #                 logging.info("Discarding "+hand[i])
    #                 return {"play": "discard " + hand.pop(i)}
    #
    #         logging.info("Discarding " + hand[i])
    #         return {"play": "discard " + hand.pop(i)}
    #
    #
    # # We should be able to meld.
    #
    # # First, find the card we discard - if needed
    # discard_string = ""
    # print(of_a_kind_count)
    #
    # if of_a_kind_count[0] > 0:
    #     if hand[-1][0] != hand[-2][0]:
    #         discard_string = " discard " + hand.pop()
    #     else:
    #         for i in range(len(hand)-2, -1, -1):
    #             if i == 0:
    #                 discard_string = " discard " + hand.pop(0)
    #                 break
    #             if hand[i][0] != hand[i - 1][0] and hand[i][0] != hand[i + 1][0]:
    #                 discard_string = " discard " + hand.pop(i)
    #                 break
    #
    # # generate our list of meld
    # play_string = ""
    # last_card = ""
    # while len(hand) > 0:
    #     card = hand.pop(0)
    #     if str(card)[0] != last_card:
    #         play_string += "meld "
    #     play_string += str(card) + " "
    #     last_card = str(card)[0]
    #
    # # remove the extra space, and add in our discard if any
    # play_string = play_string[:-1]
    # play_string += discard_string
    #
    # logging.info("Playing: "+play_string)
    # return {"play":play_string}

def get_melds(hand):
    """Identifies and returns valid melds from a hand."""
    hand.sort()
    melds = []
    i = 0
    while i < len(hand):
        current_card = hand[i]
        run = [current_card]
        kind = [current_card]
        j = i + 1
        while j < len(hand) and hand[j][0] == current_card[0]:  # Check for same rank (kind)
            kind.append(hand[j])
            j += 1

        # Run Detection (Corrected):
        numerical_rank_current = get_numerical_rank(current_card)
        while j < len(hand):
            next_card = hand[j]
            numerical_rank_next = get_numerical_rank(next_card)
            if next_card[-1] == current_card[-1] and numerical_rank_next == numerical_rank_current + (j - i):
                run.append(next_card)
                j += 1
            else:
                break


        if len(kind) >= 3:
            melds.append(kind)
        if len(run) >= 3:
            melds.append(run)
        i = j

    return melds

def get_numerical_rank(card):
    """Converts card rank to a numerical value (A=1, J=11, Q=12, K=13)."""
    rank = card[:-1]
    try:
        return int(rank)
    except ValueError:
        if rank == 'A':
            return 1
        elif rank == 'J':
            return 11
        elif rank == 'Q':
            return 12
        elif rank == 'K':
            return 13
        else:
            return 0  # Handle invalid ranks (shouldn't happen)

@app.get("/shutdown")
async def shutdown_API():
    """ Game Server calls this endpoint to shut down the player's client after testing is completed.  Only used if DEBUG is True. """
    os.kill(os.getpid(), signal.SIGTERM)
    logging.info("Player client shutting down...")
    return fastapi.Response(status_code=200, content='Server shutting down...')


''' Main code here - registers the player with the server via API call, and then launches the API to receive game information '''
if __name__ == "__main__":

    if DEBUG:
        url = "http://127.0.0.1:16200/test"

        # TODO - Change logging.basicConfig if you want
        logging.basicConfig(filename="RummyPlayer.log", format='%(asctime)s - %(levelname)s - %(message)s',
                        datefmt='%Y-%m-%d %H:%M:%S', level=logging.INFO)

    else:
        url = "http://127.0.0.1:16200/register"
        # TODO - Change logging.basicConfig if you want
        logging.basicConfig(filename="RummyPlayer.log", format='%(asctime)s - %(levelname)s - %(message)s',
                           datefmt='%Y-%m-%d %H:%M:%S', level=logging.WARNING)

    load_game_state()


    payload = {
        "name": USER_NAME,
        "address": "127.0.0.1",
        "port": str(PORT)
    }

    # noinspection PyBroadException
    try:
        # Call the URL to register client with the game server
        response = requests.post(url, json=payload)
    except Exception as e:
        print("Failed to connect to server.  Please contact Mr. Dole.")
        exit(1)

    if response.status_code == 200:
        print("Request succeeded.")
        print("Response:", response.json())  # or response.text
    else:
        print("Request failed with status:", response.status_code)
        print("Response:", response.text)
        exit(1)

    # run the client API using uvicorn
    uvicorn.run(app, host="127.0.0.1", port=PORT)
