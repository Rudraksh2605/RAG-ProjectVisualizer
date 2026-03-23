Generating class_diagram with target_model=qwen2.5-coder
[Embeddings] Fallback to LLM model for embeddings: qwen2.5-coder:latest

[LLM Router] Routing 'class_diagram' task to model: qwen2.5-coder


--- RESULT ---


@startuml
skinparam defaultFontName "Segoe UI"
skinparam defaultFontSize 13
skinparam shadowing false
skinparam roundCorner 10
skinparam BackgroundColor #FEFEFE
skinparam ArrowColor #1565C0
skinparam ArrowFontColor #333333
skinparam ArrowFontSize 12
skinparam ArrowThickness 1.5
skinparam noteBorderColor #FFB300
skinparam noteBackgroundColor #FFF9C4
skinparam noteFontColor #333333
skinparam titleFontSize 18
skinparam titleFontColor #1a1a2e
skinparam titleFontStyle bold
skinparam ClassBackgroundColor #E3F2FD
skinparam ClassBorderColor #1976D2
skinparam ClassFontColor #1a1a2e
skinparam ClassAttributeFontColor #37474F
skinparam ClassStereotypeFontColor #7B1FA2
skinparam PackageBackgroundColor #F3E5F5
skinparam PackageBorderColor #7B1FA2
skinparam PackageFontColor #4A148C
skinparam ComponentBackgroundColor #E8F5E9
skinparam ComponentBorderColor #388E3C
skinparam ComponentFontColor #1B5E20
skinparam UsecaseBackgroundColor #E3F2FD
skinparam UsecaseBorderColor #1565C0
skinparam UsecaseFontColor #0D47A1
skinparam ActorBorderColor #1565C0
skinparam ActorFontColor #1a1a2e
skinparam StateBackgroundColor #E8EAF6
skinparam StateBorderColor #283593
skinparam StateFontColor #1A237E
skinparam ParticipantBackgroundColor #E3F2FD
skinparam ParticipantBorderColor #1565C0
skinparam ParticipantFontColor #0D47A1
skinparam DatabaseBackgroundColor #FFF3E0
skinparam DatabaseBorderColor #E65100
skinparam DatabaseFontColor #BF360C
skinparam CloudBackgroundColor #E0F7FA
skinparam CloudBorderColor #00838F
skinparam CloudFontColor #006064
skinparam NodeBackgroundColor #F3E5F5
skinparam NodeBorderColor #6A1B9A
skinparam NodeFontColor #4A148C
skinparam SequenceLifeLineBorderColor #1565C0
skinparam SequenceGroupBackgroundColor #E8EAF6
title "Class Diagram — SelectiveCaller"

package "Data" {
    class ContactRepository <<Repository>> {
        - context: Context
        + getContacts(): List<Contact>
        + saveContact(contact: Contact)
    }

    class DatabaseModule <<DI Module>> {
        + provideAppDatabase(context: Context): AppDatabase
        + provideSelectedContactDao(database: AppDatabase): SelectedContactDao
    }
}

package "Domain" {
    class CheckCallAllowedUseCase <<Class>> {
        - settingsRepository: SettingsRepository
        + invoke(phoneNumber: String?): Boolean
    }

    class GetOnboardingCompletedUseCase <<Class>> {
        - settingsRepository: SettingsRepository
        + invoke(): Flow<Boolean>
    }
}

package "Business Logic" {
    class SelectiveCallScreeningService <<Service>> {
        + onScreenCall(callDetails: Call.Details)
    }

    class SetOnboardingCompletedUseCase <<Class>> {
        - settingsRepository: SettingsRepository
        + invoke(completed: Boolean)
    }
}

ContactRepository --|> RepositoryModule : provided by
SelectiveCallScreeningService ..|> CheckCallAllowedUseCase : uses
GetOnboardingCompletedUseCase ..|> SettingsRepository : accesses
@enduml
