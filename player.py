import requests
from fastapi import FastAPI, Depends
import fastapi
from pydantic import BaseModel
import uvicorn
import os
import signal
import logging

from main import RummyGameState

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
USER_NAME = "j"
# TODO - change your method of saving information from the very rudimentary method here
hand = [] # list of cards in our hand
discard = [] # list of cards organized as a stack
cannot_discard = ""

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
        if (USER_NAME + " draws" in event_line or (USER_NAME + " takes") in event_line):
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
    process_events(update_info.event, state)  # Pass state to process_events

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
    process_events(update_info.event, state)
    of_a_kind_counts = get_of_a_kind_count(state.hand)

    if sum(of_a_kind_counts[0:2]) > 1:  # More Pythonic way to check for unmeldable cards
        return handle_discard(state, of_a_kind_counts)  # Separate function for discard logic

    return handle_meld(state) # Separate function for meld logic

def handle_discard(state: RummyGameState, of_a_kind_counts):
    if of_a_kind_counts[0] > 0:  # Single cards to discard
        card_to_discard = find_single_card_to_discard(state.hand)
        if card_to_discard:
            state.hand.remove(card_to_discard)
            logging.info(f"Discarding single card: {card_to_discard}")
            return {"play": f"discard {card_to_discard}"}

    elif of_a_kind_counts[1] > 0:  # Pairs to discard
        card_to_discard = find_pair_to_discard(state.hand, state.cannot_discard)
        if card_to_discard:
          state.hand.remove(card_to_discard)
          logging.info(f"Discarding pair: {card_to_discard}")
          return {"play": f"discard {card_to_discard}"}

    #Shouldn't happen, but just in case
    card_to_discard = state.hand.pop()
    logging.info(f"Discarding (Default): {card_to_discard}")
    return {"play": f"discard {card_to_discard}"}

def find_single_card_to_discard(hand):
    if len(hand) > 1 and hand[-1][0] != hand[-2][0]: #Last card is a single
        return hand[-1]
    for i in range(len(hand) - 2, -1, -1):
        if hand[i][0] != hand[i - 1][0] and hand[i][0] != hand[i + 1][0]:
            return hand[i]
    return hand[0] #If we get here, all cards are pairs or better. Return the first card.

def find_pair_to_discard(hand, cannot_discard):
  for card in reversed(hand): #Iterate backwards through the hand
      if card != cannot_discard and get_count(hand, card) == 2:
          return card
  return None #If we get here, no suitable pair was found.

def handle_meld(state: RummyGameState):
    discard_card = None
    if state.hand and get_count(state.hand, state.hand[-1]) == 1: #If the last card is a single, we are discarding it
        discard_card = state.hand.pop()

    meld_string = "meld "
    last_rank = None
    cards_to_meld = []

    for card in state.hand: #Gather cards for melding first
        if card[0] != last_rank:
            cards_to_meld.append([])
        cards_to_meld[-1].append(card)
        last_rank = card[0]

    for meld_group in cards_to_meld: #Create the meld string
        meld_string += " ".join(meld_group) + " "

    meld_string = meld_string[:-1]  # Remove trailing space

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