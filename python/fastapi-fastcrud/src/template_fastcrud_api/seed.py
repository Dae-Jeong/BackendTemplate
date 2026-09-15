"""Create a local experiment product once; never reset existing inventory."""

import argparse
import asyncio
import json

from sqlalchemy.ext.asyncio import async_sessionmaker

from template_fastcrud_api.core.database import create_primary_engine, primary_session
from template_fastcrud_api.core.database_metrics import create_database_metrics
from template_fastcrud_api.core.metrics import create_metrics
from template_fastcrud_api.core.settings import Settings
from template_fastcrud_api.repositories.reservations import seed_product
from template_fastcrud_api.schemas.reservations import ReserveRequest


async def seed(product_id: str, stock: int) -> None:
    settings = Settings()
    if not settings.db_primary_url:
        raise ValueError("Set DB_PRIMARY_URL before seeding")
    metrics = create_database_metrics(
        create_metrics(), settings.db_pool_size + settings.db_pool_max_overflow
    )
    engine = create_primary_engine(settings, metrics)
    try:
        async with (
            primary_session(async_sessionmaker(engine), metrics) as session,
            session.begin(),
        ):
            product = await seed_product(session, product_id, stock)
        print(
            json.dumps(
                {"product_id": product.product_id, "available": product.available}
            )
        )
    finally:
        await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--product-id", default="demo")
    parser.add_argument("--stock", type=int, default=10)
    args = parser.parse_args()
    if not 0 <= args.stock <= 1_000_000:
        parser.error("stock must be between 0 and 1000000")
    product_id = ReserveRequest(product_id=args.product_id).product_id
    asyncio.run(seed(product_id, args.stock))


if __name__ == "__main__":
    main()
