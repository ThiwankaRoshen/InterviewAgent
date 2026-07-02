import type { StageItem } from '../types/session'

interface StageItemCardProps {
  stage: StageItem
  onSelect: (stage: StageItem) => void
  isLoading: boolean
}

export function StageItemCard({ stage, onSelect, isLoading }: StageItemCardProps) {
  return (
    <button
      type="button"
      className="stage-item-card"
      onClick={() => onSelect(stage)}
      disabled={isLoading}
    >
      <div className="stage-item-card__header">
        <h4 className="stage-item-card__title">{stage.stage_name}</h4>
        <span className="stage-item-card__order">Stage {stage.stage_order}</span>
      </div>
      <p className="stage-item-card__description">{stage.stage_description}</p>
      <div className="stage-item-card__action">
        <span className="stage-item-card__cta">Start Practice →</span>
      </div>
    </button>
  )
}
