headerModUI <- function(id) {
  
  ns <- NS(id)
  
  uiOutput(ns("ecm_header"))
  
}

headerMod <- function(input, output, session, credentials, pool, id_tab) {
  
  
  output$constructor_operator <- renderUI({
    
    ns <- session$ns
    
    fleetsummary <- pool %>% tbl(in_schema("ecmapp", "_fleetsummary")) %>% collect()

    userdefault_test <- pool %>%
      tbl(in_schema("utair", "userdefault_test")) %>%
      filter(
        user %in% !!credentials()$user
      ) %>%
      collect()

    if(nrow(userdefault_test) == 0){

      selected <- unique(fleetsummary$operator)[1]

    }
    else{

      selected <- jsonlite::fromJSON(userdefault_test$default)$enginetrends_operator_pi

    }
    
    pickerInput(
      ns("constructor_operator_pi"),
      label = "Operator",
      choices = unique(fleetsummary$operator), #"utair", 
      options = list(
        `live-search`=TRUE,
        `actions-box` = TRUE,
        `deselect-all-text` = "deselect",
        `select-all-text` = "select all",
        `none-selected-text` = "zero"
      ),
      selected = selected, #"utair",
      multiple = F
    )
    
  })
  
  output$constructor_actype <- renderUI({
    
    ns <- session$ns
    # browser()
    choices <- pool %>%
      tbl(in_schema("ecmapp", "_fleetsummary")) %>%
      filter(
        operator %in% !!input$constructor_operator_pi
      ) %>%
      group_by(
        operator,
        aircraft_type
      ) %>%
      summarise(
        count_ac = n_distinct(aircraft_id)
      ) %>%
      collect()

    userdefault_test <- pool %>%
      tbl(in_schema("utair", "userdefault_test")) %>%
      filter(
        user %in% !!credentials()$user
      ) %>%
      collect()

    if(nrow(userdefault_test) == 0){

      selected <- choices$aircraft_type[1]

    }
    else{

      selected <- jsonlite::fromJSON(userdefault_test$default)$enginetrends_actype_pi

    }
    
    pickerInput(
      ns("constructor_actype_pi"),
      label = "A/C Type:", 
      choices = lapply(split(choices$aircraft_type, choices$operator), as.list),
      choicesOpt = list(
        subtext = unlist(lapply(split(choices$count_ac, choices$operator), as.list))
      ), 
      options = list(
        `live-search`=TRUE,
        `actions-box` = TRUE,
        `deselect-all-text` = "deselect",
        `select-all-text` = "select all",
        `none-selected-text` = "zero"
      ),
      selected = selected,
      multiple = F
    )
    
  })
  
  output$constructor_acreg <- renderUI({
    
    ns <- session$ns
    
    # req(input$enginetrends_operator_pi, input$enginetrends_actype_pi)
    
    choices <- NULL
    
    choicesOpt <- NULL
    
    selected <- NULL
    # browser()
    if(!is.null(input$constructor_actype_pi) & !is.null(input$constructor_operator_pi)){
      
      fleetsummary <- pool %>%
        tbl(in_schema("ecmapp", "_fleetsummary")) %>%
        filter(
          operator %in% !!input$constructor_operator_pi,
          aircraft_type %in% !!input$constructor_actype_pi,
          is.na(removal_datetime),
          !is.na(ac_reg_new),
          ac_reg_new != "-"
        ) %>%
        collect()
      
      fleetsummary <- fleetsummary[!duplicated(fleetsummary),]
      
      fleetsummary <- fleetsummary %>% 
        group_by(
          aircraft_id, 
          engine_position
        ) %>%
        filter(
          install_datetime == max(install_datetime)
        )
      
      df_choices <- fleetsummary[,c(
        "aircraft_type",
        "ac_reg_new",
        "ac_reg_old",
        "aircraft_id",
        "engine_position",
        "engine_id"
      )] %>%
        group_by(
          aircraft_type,
          ac_reg_new,
          ac_reg_old,
          aircraft_id
        ) %>%
        tidyr::pivot_wider(
          names_from = engine_position,
          names_prefix = "esn_",
          values_from = c(
            engine_id
          )
        ) %>%
        mutate(
          subtext = paste0(
            ac_reg_old,
            " ",
            aircraft_id,
            ", pos.1: ",
            esn_1,
            ", pos.2: ",
            esn_2
          )
        )
      
      
      choices <- lapply(split(df_choices$ac_reg_new, df_choices$aircraft_type), as.list)
      
      choicesOpt <- list(
        subtext = unlist(lapply(split(df_choices$subtext, df_choices$aircraft_type), as.list))
      )
      
      userdefault_test <- pool %>% 
        tbl(in_schema("utair", "userdefault_test")) %>% 
        filter(
          user %in% !!credentials()$user
        ) %>%
        collect()
      
      if(nrow(userdefault_test) == 0){
        
        selected <- choices$ac_reg_new[1]
        
      }
      
      else{
        
        selected <- jsonlite::fromJSON(userdefault_test$default)$enginetrends_acreg_pi
        
      }
      
    }
    
    pickerInput(
      ns("constructor_acreg_pi"),
      label = "A/C Reg:", 
      choices = choices,
      choicesOpt = choicesOpt, 
      options = list(
        `live-search`=TRUE,
        `dropdown-align-right` = TRUE
      ),
      selected = selected,
      multiple = T
    )
    
  })
  
  output$constructor_parameters_takeoff <- renderUI({
    
    ns <- session$ns
    browser()
    parameters <- pool %>%
      tbl(in_schema("ecmapp", "parameters")) %>%
      filter(
        aircraft_type %in% !!input$constructor_actype_pi,
        flight_phase == !!"TAKEOFF"
      ) %>%
      collect()
    
    choices_list <- list()
    
    choices_opt_list <- list()
    
    for(table_name in unique(parameters$table_name)){
      
      choices_list[[table_name]] <- parameters$parameter_name[parameters$table_name == table_name]
      
      choices_opt_list[[table_name]] <- parameters$param_description[parameters$table_name == table_name]
      
    }
    
    pickerInput(
      ns("constructor_parameters_takeoff_pi"),
      label = "Parameters TAKEOFF",
      choices = choices_list, 
      choicesOpt = list(
        subtext = unlist(choices_opt_list)
      ),
      # selected = "TAKE OFF trends (MAIN)",
      options = list(
        `live-search`=TRUE
      ),
      multiple = T
    )
    
  })
  
  output$constructor_parameters_cruise <- renderUI({
    
    ns <- session$ns
    # browser()
    parameters <- pool %>%
      tbl(in_schema("ecmapp", "parameters")) %>%
      filter(
        aircraft_type %in% !!input$constructor_actype_pi,
        flight_phase == !!"CRUISE"
      ) %>%
      collect()
    
    choices_list <- list()
    
    choices_opt_list <- list()
    
    for(table_name in unique(parameters$table_name)){
      
      choices_list[[table_name]] <- parameters$parameter_name[parameters$table_name == table_name]
      
      choices_opt_list[[table_name]] <- parameters$param_description[parameters$table_name == table_name]
      
    }
    
    pickerInput(
      ns("constructor_parameters_cruise_pi"),
      label = "Parameters CRUISE",
      choices = choices_list, 
      choicesOpt = list(
        subtext = unlist(choices_opt_list)
      ),
      # selected = "TAKE OFF trends (MAIN)",
      options = list(
        `live-search`=TRUE
      ),
      multiple = T
    )
    
  })
  
  output$constructor_parameters_climb <- renderUI({
    
    ns <- session$ns
    # browser()
    parameters <- pool %>%
      tbl(in_schema("ecmapp", "parameters")) %>%
      filter(
        aircraft_type %in% !!input$constructor_actype_pi,
        flight_phase == !!"CLIMB"
      ) %>%
      collect()
    
    choices_list <- list()
    
    choices_opt_list <- list()
    
    for(table_name in unique(parameters$table_name)){
      
      choices_list[[table_name]] <- parameters$parameter_name[parameters$table_name == table_name]
      
      choices_opt_list[[table_name]] <- parameters$param_description[parameters$table_name == table_name]
      
    }
    
    pickerInput(
      ns("constructor_parameters_climb_pi"),
      label = "Parameters CLIMB",
      choices = choices_list, 
      choicesOpt = list(
        subtext = unlist(choices_opt_list)
      ),
      # selected = "TAKE OFF trends (MAIN)",
      options = list(
        `live-search`=TRUE
      ),
      multiple = T
    )
    
  })
  
  output$constructor_plotoptions <- renderUI({
    
    ns <- session$ns
    
    dropdownButton(
      
      inputId = "mydropdown_constructor",
      label = "Plot options",
      icon = icon("gear"),
      status = "default",
      circle = FALSE,
      tooltip = tooltipOptions(title = "Click to see options !"),
      accordion(
        id = "plotoptionsaccotdion_constructor",
        
        accordionItem(
          id = "accordion_item_0_constructor",
          title = "Position",
          status = "warning",
          collapsed = FALSE,
          
          radioButtons(
            ns("rb_engine_position_constructor"), 
            label = NULL,
            choices = list(
              "All" = 1,
              "Engine pos. 1" = 2,
              "Engine pos. 2" = 3
            ), 
            selected = 1
          )
        ),
        
        accordionItem(
          id = "accordion_item_1_constructor",
          title = "Smooth",
          status = "warning",
          collapsed = FALSE,
          
          radioButtons(
            ns("rb_enable_smooth_constructor"), 
            label = NULL,
            choices = list(
              "Only smooth" = 1,
              "Only raw" = 2,
              "Smooth and raw" = 3
            ), 
            selected = 3
          ),
          numericInput(
            ns("smooth_window_constructor"),
            label = NULL,
            15, 
            min = 1, 
            max = 100
          )
        ),
        accordionItem(
          id = "accordion_item_3_constructor",
          title = "Alerts/Maintenance",
          status = "warning",
          collapsed = FALSE,
          checkboxGroupInput(
            ns("cgi_show_alerts_constructor"),
            label = NULL,
            choices = c(
              "Show alerts",
              "Show maintenance actions",
              "Show previous installations"
            ),
            selected = c(
              "Show alerts",
              "Show previous installations"
            ),
            inline = FALSE
          )
        ),
        accordionItem(
          id = "accordion_item_4_constructor",
          title = "Graph size/range",
          status = "warning",
          collapsed = FALSE,
          radioGroupButtons(
            ns("rb_graph_size_constructor"),
            label = NULL,
            size = "sm",
            status = "warning",
            choices = c(
              `<i class='fa fa-th-large'></i>` = "multiple", 
              `<i class='fa fa-th-list'></i>` = "line", 
              `<i class='fa fa-stop'></i>` = "one"
            ),
            selected = "one",
            justified = FALSE
          ),
          radioButtons(
            ns("rb_range_selector_constructor"), 
            label = NULL,
            choices = list(
              "1m",
              "3m",
              "6m",
              "YTD",
              "1y",
              "ALL"
            ), 
            selected = "ALL"
          )
        )
      )
    )
    
  })
  
  
  output$ecm_header <- renderUI({
    
    ns <- session$ns
    # browser()
    # if(id_tab() == "engine_trends"){
    #   
    #   
    # }
     if(id_tab() == "constructor"){
      
    }
    
    
  })
  
  headerselectors <- list(
    enginetrends = list(
      update_enginetrends_data = reactive({input$update_enginetrends_data}),
      ab_next = reactive({input$ab_next}),
      ab_prev = reactive({input$ab_prev}),
      enginetrends_operator_pi = reactive({input$enginetrends_operator_pi}),
      enginetrends_actype_pi = reactive({input$enginetrends_actype_pi}),
      enginetrends_acreg_pi = reactive({input$enginetrends_acreg_pi}),
      enginetrends_presetname_pi = reactive({input$enginetrends_presetname_pi}),
      plotoptions = list(
        rb_enable_smooth = reactive({input$rb_enable_smooth}),
        smooth_window = reactive({input$smooth_window}),
        cgi_show_alerts = reactive({input$cgi_show_alerts}),
        rb_graph_size = reactive({input$rb_graph_size}),
        rb_range_selector = reactive({input$rb_range_selector}),
        rb_engine_position = reactive({input$rb_engine_position})
      )
    ),
    fleetreports = list(
      update_fleetreport_data = reactive({input$update_fleetreport_data}),
      fleetreports_operator_pi = reactive({input$fleetreports_operator_pi}),
      fleetreports_actype_pi = reactive({input$fleetreports_actype_pi}),
      fleetreports_acreg_pi = reactive({input$fleetreports_acreg_pi}),
      fleetreports_presetname_pi = reactive({input$fleetreports_presetname_pi}),
      plotoptions = list(
        fleetreports_datestart_di = reactive({input$fleetreports_datestart_di}),
        fleetreports_dateend_di = reactive({input$fleetreports_dateend_di})
      )
    ),
    maintenance = list(
      update_maintenance_data = reactive({input$update_maintenance_data}),
      maintenance_operator_pi = reactive({input$maintenance_operator_pi}),
      maintenance_actype_pi = reactive({input$maintenance_actype_pi}),
      maintenance_acreg_pi = reactive({input$maintenance_acreg_pi})
    ),
    alerts = list(
      update_alerts_data = reactive({input$update_alerts_data}),
      alerts_operator_pi = reactive({input$alerts_operator_pi}),
      alerts_actype_pi = reactive({input$alerts_actype_pi}),
      alerts_acreg_pi = reactive({input$alerts_acreg_pi})
    ),
    dataquality = list(
      update_dataquality_data = reactive({input$update_dataquality_data}),
      dataquality_operator_pi = reactive({input$dataquality_operator_pi})
    ),
    constructor = list(
      update_constructor_data = reactive({input$update_constructor_data}),
      constructor_operator_pi = reactive({input$constructor_operator_pi}),
      constructor_actype_pi = reactive({input$constructor_actype_pi}),
      constructor_acreg_pi = reactive({input$constructor_acreg_pi}),
      # constructor_presetname_pi = reactive({input$constructor_presetname_pi}),
      constructor_parameters_takeoff_pi = reactive({input$constructor_parameters_takeoff_pi}),
      constructor_parameters_cruise_pi = reactive({input$constructor_parameters_cruise_pi}),
      constructor_parameters_climb_pi = reactive({input$constructor_parameters_climb_pi}),
      plotoptions = list(
        rb_enable_smooth = reactive({input$rb_enable_smooth_constructor}),
        smooth_window = reactive({input$smooth_window_constructor}),
        cgi_show_alerts = reactive({input$cgi_show_alerts_constructor}),
        rb_graph_size = reactive({input$rb_graph_size_constructor}),
        rb_range_selector = reactive({input$rb_range_selector_constructor}),
        rb_engine_position = reactive({input$rb_engine_position_constructor})
      )
    ),
    useroptions = list(
      ab_save_useroptions = reactive({input$ab_save_useroptions})
    )
  )
  
  return(headerselectors)
}
