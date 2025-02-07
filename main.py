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
        self.hand_over = False

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
    game_state.hand = game_info.hand.split(" ")  # Correct
    game_state.hand.sort()
    game_state.discard_pile = []  # Correct
    logging.info("2p game started, hand is " + str(game_state.hand))
    return {"status": "OK"}

# data class used to receive data from API POST
class HandInfo(BaseModel):
    hand: str


@app.post("/start-2p-hand/")
async def start_hand(hand_info: HandInfo):
    """Game Server calls this endpoint to inform player a new hand is starting."""
    game_state.hand = hand_info.hand.split(" ")
    game_state.hand.sort()
    game_state.discard_pile = []  # Important: Reset discard pile for the new hand

    logging.info("2p hand started, hand is " + str(game_state.hand))

    # Save the updated game state (optional, but good practice):
    game_state_dict = {
        "hand": game_state.hand,
        "discard": game_state.discard_pile  # Save the (empty) discard pile
    }
    with open("game_state.json", "w") as f:
        json.dump(game_state_dict, f)

    return {"status": "OK"}

def process_events(event_text):
    """Shared function to process event text."""
    global game_state  # Important: Declare game_state as global

    for event_line in event_text.splitlines():
        if (USER_NAME + " draws") in event_line or (USER_NAME + " takes") in event_line:
            drawn_card = event_line.split(" ")[-1]
            game_state.hand.append(drawn_card)  # Update game_state.hand
            game_state.hand.sort()
            logging.info(f"Drew a {drawn_card}, hand is now: {game_state.hand}")
        elif "discards" in event_line:  # Use elif for efficiency
            parts = event_line.split()
            if len(parts) > 2: # Check if the format is correct
                discarded_card = parts[-1]
                game_state.discard_pile.insert(0, discarded_card)  # Update game_state.discard_pile
                logging.info(f"Opponent discarded: {discarded_card}") # Log the discard
        elif "takes" in event_line:  # Use elif
            if game_state.discard_pile:
                game_state.discard_pile.pop(0)  # Update game_state.discard_pile
                logging.info("Opponent took from discard pile") # Log the action
            else:
                logging.warning("Opponent tried to take from empty discard pile.")
        elif "Ends:" in event_line:  # Check for end of hand/game
            parts = event_line.split()
            if len(parts) > 3 and parts[2].isdigit() and parts[4].isdigit(): # Check if the format is correct
                player1_score = int(parts[2])
                player2_score = int(parts[4])
                if player1_score >= 2000 or player2_score >= 2000:
                    game_state.is_game_over = True
                    logging.info("Game Over!")
                game_state.hand_over = True # set hand_over to true
                logging.info("Hand Over!")
            else:
                logging.warning(f"Invalid 'Ends:' event format: {event_line}") # Log if the format is incorrect

        elif "meld" in event_line:
            parts = event_line.split()
            if len(parts) > 1: # Check if the format is correct
                meld_cards = parts[1:]
                logging.info(f"Opponent melded: {meld_cards}") # Log the meld
            else:
                logging.warning(f"Invalid 'meld' event format: {event_line}") # Log if the format is incorrect

        elif "discard" in event_line and USER_NAME not in event_line:  # opponent discarded
            parts = event_line.split()
            if len(parts) > 1: # Check if the format is correct
                discarded_card = parts[-1]
                game_state.discard_pile.insert(0, discarded_card)  # Update game_state.discard_pile
                logging.info(f"Opponent discarded: {discarded_card}") # Log the discard
            else:
                logging.warning(f"Invalid 'discard' event format: {event_line}") # Log if the format is incorrect

        elif "draw stock" in event_line and USER_NAME not in event_line:  # opponent drew stock
                logging.info("Opponent drew from stock") # Log the action

        elif "draw discard" in event_line and USER_NAME not in event_line:  # opponent drew discard
                logging.info("Opponent drew from discard") # Log the action

# data class used to receive data from API POST
class UpdateInfo(BaseModel):
    game_id: str
    event: str

@app.post("/update-2p-game/")
async def update_2p_game(update_info: UpdateInfo):
    """Game Server calls this endpoint."""
    global game_state  # Make sure game_state is global
    process_events(update_info.event)

    # Save the updated game state (using game_state.hand and game_state.discard_pile):
    game_state_dict = {
        "hand": game_state.hand,
        "discard": game_state.discard_pile
    }
    with open("game_state.json", "w") as f:
        json.dump(game_state_dict, f)

    return {"status": "OK"}


def load_game_state():
    global game_state
    try:
        with open("game_state.json", "r") as f:
            loaded_state = json.load(f)
            game_state.hand = loaded_state.get("hand", [])       # Correct
            game_state.discard_pile = loaded_state.get("discard", []) # Correct
            # game_state.stock = loaded_state.get("stock", [])  # If you were saving stock
            logging.info(f"Game state loaded: Hand - {game_state.hand}, Discard - {game_state.discard_pile}")
    except FileNotFoundError:
        logging.warning("Game state file not found, starting with an empty state.")


@app.post("/draw/")
async def draw():
    """Game Server calls this endpoint to start player's turn."""
    if game_state.is_game_over:
        return {"play": "error", "message": "Game is over"}

    if game_state.hand_over:
        return {"play": "error", "message": "Hand is over"}

    if not game_state.discard_pile and not game_state.stock:
        game_state.hand_over = True # If nothing to draw from, hand is over
        return {"play": "end", "message": "No cards left to draw"} # Signal end of hand

    if not game_state.discard_pile:
        card = game_state.stock.pop() # Draw from stock
        game_state.hand.append(card)
        game_state.hand.sort()
        logging.info(f"Drew {card} from stock. Hand: {game_state.hand}")
        return {"play": "draw stock"}

    top_discard = game_state.discard_pile[0]

    if any(top_discard[0] == c[0] for c in game_state.hand): # Check if top discard is playable
        card = game_state.discard_pile.pop(0) # Draw from discard
        game_state.hand.append(card)
        game_state.hand.sort()
        logging.info(f"Drew {card} from discard. Hand: {game_state.hand}")
        return {"play": "draw discard"}
    else:
        card = game_state.stock.pop() # Draw from stock
        game_state.hand.append(card)
        game_state.hand.sort()
        logging.info(f"Drew {card} from stock. Hand: {game_state.hand}")
        return {"play": "draw stock"}



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
    global current_turn  # If you want current_turn to be global

    if current_turn == "Player 1":
        if action == "discard":
            if game_state.hand:  # Check if the hand is not empty
                discard_card = game_state.hand.pop()
                if not validate_discard(game_state.hand, discard_card):
                    return {"error": "Cannot discard that card"}
                game_state.discard_pile.append(discard_card)
                logging.info(f"Player 1 discarded: {discard_card}") # Log the discard
            else:
                logging.warning("Player 1 tried to discard from an empty hand.")
                return {"error": "Cannot discard from an empty hand"} # Return an error


        current_turn = "Player 2"
    elif current_turn == "Player 2":
        if action == "discard":
            if game_state.hand:  # Check if the hand is not empty
                discard_card = game_state.hand.pop()
                if not validate_discard(game_state.hand, discard_card):
                    return {"error": "Cannot discard that card"}
                game_state.discard_pile.append(discard_card)
                logging.info(f"Player 2 discarded: {discard_card}") # Log the discard
            else:
                logging.warning("Player 2 tried to discard from an empty hand.")
                return {"error": "Cannot discard from an empty hand"} # Return an error

        current_turn = "Player 1"
    else:
        logging.warning("Invalid current_turn value.")
        return {"error": "Invalid turn"}

    return {"status": "OK", "current_turn": current_turn}

def check_end_of_game():
    """ Check if any player has completed their hand (no cards left) """
    if not game_state.hand:
        return True
    return False


@app.post("/lay-down/")
async def lay_down(update_info: UpdateInfo):
    global cannot_discard

    if game_state.is_game_over:
        return {"play": "error", "message": "Game is over"}

    if game_state.hand_over:
        return {"play": "error", "message": "Hand is over"}

    process_events(update_info.event)

    if game_state.hand_over:  # Check again after processing events
        return {"play": "error", "message": "Hand is over"}

    melds = get_melds(game_state.hand)

    if melds:
        play_string = ""
        cards_to_remove = []

        for meld in melds:  # Play all melds (or your chosen strategy)
            play_string += "meld "
            for card in meld:
                play_string += str(card) + " "
                cards_to_remove.append(card)

        for card in cards_to_remove:
            game_state.hand.remove(card)

        melds.clear()

        if game_state.hand: # Check if hand is empty after melding
            discard_card = game_state.hand.pop()
            play_string += "discard " + str(discard_card)
        else:
            game_state.hand_over = True # If hand is empty, hand is over
            return {"play": "error", "message": "Hand is over"} # Return because hand is over

        play_string = play_string.strip()
        logging.info(f"Playing: {play_string} (Melding and discarding)")
        return {"play": play_string}  # Return immediately after playing meld!

    else:  # No melds found
        if game_state.hand:
            discard_card = game_state.hand.pop()
            play_string = "discard " + str(discard_card)
            logging.info(f"Playing: {play_string} (Discarding)")
            return {"play": play_string}
        else:
            game_state.hand_over = True
            return {"play": "end"}


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