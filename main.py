import requests
from fastapi import FastAPI, Depends
import fastapi
from pydantic import BaseModel
import uvicorn
import os
import signal
import logging

# from main import RummyGameState

#import pytest

"""
By Todd Dole, Revision 1.2
Written for Hardin-Simmons CSCI-4332 Artificial Intelligence
Revision History
1.0 - API setup
1.1 - Very basic test player
1.2 - Bugs fixed and player improved, should no longer forfeit
"""

# TODO - Change the PORT and USER_NAME Values before running
DEBUG = True
PORT = 10001
USER_NAME = "crustacean_cheapskate"
# TODO - change your method of saving information from the very rudimentary method here
# hand = [] # list of cards in our hand
# discard = [] # list of cards organized as a stack
cannot_discard = ""

class RummyGameState:
    def __init__(self):
        self.hand = []
        self.discard_pile = []
        self.cannot_discard = ""
        self.opponent_name = ""  # Store opponent's name
        self.game_id = ""       # Store the game ID

    def reset_hand(self, hand_str):
        self.hand = hand_str.split(" ")
        self.hand.sort()

    def add_to_hand(self, card):
        self.hand.append(card)
        self.hand.sort()

    def add_to_discard(self, card):
        self.discard_pile.insert(0, card)

    def remove_from_discard(self):
        if self.discard_pile:  # Check if discard pile is not empty
            return self.discard_pile.pop(0)
        return None  # Or handle the case where the discard pile is empty

    def set_cannot_discard(self, card):
        self.cannot_discard = card

    def clear_cannot_discard(self):
        self.cannot_discard = ""

    def __str__(self):  # For easy debugging/logging
        return f"Game ID: {self.game_id}\nOpponent: {self.opponent_name}\nHand: {self.hand}\nDiscard: {self.discard_pile}\nCannot Discard: {self.cannot_discard}"

game_state = RummyGameState()


# set up the FastAPI application
app = FastAPI()

# Dependency function to provide the game state to endpoints
def get_game_state():
    return game_state

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
    global game_state  # Access the global game state

    game_state.game_id = game_info.game_id
    game_state.opponent_name = game_info.opponent
    game_state.reset_hand(game_info.hand)

    logging.info(f"2p game started:\n{game_state}")
    return {"status": "OK"}

# data class used to receive data from API POST
class HandInfo(BaseModel):
    hand: str

@app.post("/start-2p-hand/")
async def start_hand(hand_info: HandInfo):
    global game_state

    game_state.discard_pile = []  # Clear discard pile for new hand
    game_state.reset_hand(hand_info.hand)

    logging.info(f"2p hand started:\n{game_state}")
    return {"status": "OK"}


def process_events(event_text):
    global game_state

    for event_line in event_text.splitlines():
        if USER_NAME + " draws" in event_line or (USER_NAME + " takes") in event_line:
            card = event_line.split(" ")[-1]
            game_state.add_to_hand(card)
            logging.info(f"Drew {card}, Hand: {game_state.hand}")

        elif "discards" in event_line:
            card = event_line.split(" ")[-1]
            game_state.add_to_discard(card)

        elif "takes" in event_line:
            game_state.remove_from_discard()

        elif " Ends:" in event_line:
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
    # TODO - Your code here - update this section if you want
    process_events(update_info.event)
    print(update_info.event)
    return {"status": "OK"}

@app.post("/draw/")
async def draw(update_info: UpdateInfo, state: RummyGameState = Depends(get_game_state)):  # Inject game state
    process_events(update_info.event)  # Pass state to process_events

    if not state.discard_pile:
        state.clear_cannot_discard()
        return {"play": "draw stock"}

    top_discard = state.discard_pile[0]
    if any(top_discard[0] in card for card in state.hand):
        state.set_cannot_discard(top_discard)
        return {"play": "draw discard"}

    state.clear_cannot_discard()
    return {"play": "draw stock"}



def get_of_a_kind_count(hand):
    counts = {}  # Use a dictionary to store counts
    for card in hand:
        rank = card[0]  # Extract the rank
        counts[rank] = counts.get(rank, 0) + 1  # Increment count for this rank

    of_a_kind_count: list[int] = [0] * 4  # Initialize counts for 1-of-a-kind to 4-of-a-kind
    for count in counts.values():
        of_a_kind_count[count - 1] += 1  # Increment the appropriate count

    return of_a_kind_count


def get_count(hand, card):
    count = 0
    for check_card in hand:
        if check_card[0] == card[0]: count += 1
    return count


@app.post("/lay-down/")
async def lay_down(update_info: UpdateInfo, state: RummyGameState = Depends(get_game_state)):
    process_events(update_info.event)
    of_a_kind_counts = get_of_a_kind_count(state.hand)

    if sum(of_a_kind_counts[:2]) > 1:  # Check if discarding is necessary
        return handle_discard(state, of_a_kind_counts)

    return handle_meld(state)


def handle_discard(state: RummyGameState, of_a_kind_counts):
    # 1. Prioritize discarding single cards
    if of_a_kind_counts[0] > 0:
        card_to_discard = find_card_to_discard(state.hand, 1)  # Find a single card
        if card_to_discard:
            state.hand.remove(card_to_discard)
            logging.info(f"Discarding single card: {card_to_discard}")
            return {"play": f"discard {card_to_discard}"}

    # 2. If no singles, discard a pair (if possible and not cannot_discard)
    elif of_a_kind_counts[1] > 0:
        card_to_discard = find_card_to_discard(state.hand, 2, state.cannot_discard) # Find any pair
        if card_to_discard:
            state.hand.remove(card_to_discard)
            logging.info(f"Discarding pair: {card_to_discard}")
            return {"play": f"discard {card_to_discard}"}

    # 3. If no singles or pairs, discard anything (should be rare)
    if state.hand: #Check if the hand is empty
      card_to_discard = state.hand.pop()  # Discard the last card (arbitrarily)
      logging.info(f"Discarding (fallback): {card_to_discard}")
      return {"play": f"discard {card_to_discard}"}

    return {"play": "error"} #If we get here, something went wrong.

def find_card_to_discard(hand, count, cannot_discard=None):
    for card in reversed(hand):  # Iterate backwards for efficiency
        if (cannot_discard is None or card != cannot_discard) and get_count(hand, card) == count:
            return card
    return None  # No suitable card found




def handle_meld(state: RummyGameState):
    meld_groups = []  # List of lists, each sublist is a meld group
    current_meld_group = []
    last_rank = None

    for card in sorted(state.hand):  # Sort hand before melding
        if card[0] != last_rank and current_meld_group:  # Start a new group
            meld_groups.append(current_meld_group)
            current_meld_group = []
        current_meld_group.append(card)
        last_rank = card[0]
    meld_groups.append(current_meld_group)  # Add the last group

    meld_string = "meld"
    discard_card = None

    if state.hand and get_count(state.hand, state.hand[-1]) == 1: #If last card is a single, discard it
        discard_card = state.hand.pop()

    for meld_group in meld_groups:
        meld_string += " " + " ".join(meld_group)

    if discard_card:
        meld_string += f" discard {discard_card}"

    logging.info(f"Melding: {meld_string}")
    return {"play": meld_string}


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
                    datefmt='%Y-%m-%d %H:%M:%S',level=logging.INFO)
    else:
        url = "http://127.0.0.1:16200/register"
        # TODO - Change logging.basicConfig if you want
        logging.basicConfig(filename="RummyPlayer.log", format='%(asctime)s - %(levelname)s - %(message)s',
                    datefmt='%Y-%m-%d %H:%M:%S',level=logging.WARNING)

    payload = {
        "name": USER_NAME,
        "address": "127.0.0.1",
        "port": str(PORT)
    }

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