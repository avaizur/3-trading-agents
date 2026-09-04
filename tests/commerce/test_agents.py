from src.commerce.agents.critic import run as critic_agent_run
from src.commerce.agents.product_scout import run as scout_agent_run
from src.commerce.agents.seller_a import run as seller_a_agent_run
from src.commerce.agents.seller_b import run as seller_b_agent_run
from src.commerce.critic import run as critic_run
from src.commerce.product_scout import run as scout_run
from src.commerce.seller_a import run as seller_a_run
from src.commerce.seller_b import run as seller_b_run


def test_product_scout_placeholder():
    assert scout_agent_run() == "Product Scout not connected yet"
    assert scout_run() == "Product Scout not connected yet"


def test_seller_a_placeholder():
    assert seller_a_agent_run() == "Seller A not connected yet"
    assert seller_a_run() == "Seller A not connected yet"


def test_seller_b_placeholder():
    assert seller_b_agent_run() == "Seller B not connected yet"
    assert seller_b_run() == "Seller B not connected yet"


def test_critic_placeholder():
    assert critic_agent_run() == "Commerce Critic not connected yet"
    assert critic_run() == "Commerce Critic not connected yet"
