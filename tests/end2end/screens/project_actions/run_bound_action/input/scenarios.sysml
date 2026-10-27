package 'Scenarios' {
    part def Scenario;
    part def SteadyScenario :> Scenario;
    part def Instrument;

    part steady : SteadyScenario;
    part instrument : Instrument;
}
