class V1::ReservationsController < ApplicationController
  wrap_parameters false

  def create
    if request.headers["Idempotency-Key"].present?
      raise ReservationErrors::InvalidInput.new(
        location: [ "header", "Idempotency-Key" ],
        reason: "IDEMPOTENCY_NOT_SUPPORTED"
      )
    end

    unknown_field = request.request_parameters.keys.map(&:to_s).find { |field| field != "product_id" }
    if unknown_field
      raise ReservationErrors::InvalidInput.new(location: [ "body", unknown_field ], reason: "UNKNOWN_FIELD")
    end

    result = ReservationService.create(
      product_id: request.request_parameters["product_id"],
      clock: Rails.application.config.x.clock
    )

    render json: { data: serialize(result) }, status: :created
  end

  def show
    result = ReservationService.find(reservation_id: params[:reservation_id])

    render json: { data: serialize(result) }
  end

  private

  def serialize(result)
    {
      reservation_id: result.reservation_id,
      product_id: result.product_id,
      created_at: result.created_at.iso8601
    }
  end
end
