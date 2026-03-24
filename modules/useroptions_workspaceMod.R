useroptions_workspaceModUI <- function(id) {
  
  ns <- NS(id)
  
  uiOutput(ns("useroptions_workspace"))
  
}

useroptions_workspaceMod <- function(input, output, session, credentials, pool, headerselectors, id_tab) {
  
  ns <- session$ns
  
  output$useroptions_enginetrends_operator <- renderUI({
    
    ns <- session$ns
    
    fleetsummary <- pool %>% 
      tbl(in_schema("ecmapp", "_fleetsummary")) %>% 
      collect()
    
    userdefault_test <- pool %>% 
      tbl(in_schema("utair", "userdefault_test")) %>% 
      filter(
        user %in% !!credentials()$user
      ) %>%
      collect()
    
    if(nrow(userdefault_test) == 0){
      
      # selected <- unique(fleetsummary$operator)
      
      selected <- NULL
      
    }
    else{
      
      selected <- jsonlite::fromJSON(userdefault_test$default)$enginetrends_operator_pi
      
    }
    
    pickerInput(
      ns("useroptions_enginetrends_operator_pi"),
      label = "Operator",
      choices = unique(fleetsummary$operator), 
      options = list(
        `live-search`=TRUE,
        `actions-box` = TRUE,
        `deselect-all-text` = "deselect",
        `select-all-text` = "select all",
        `none-selected-text` = "zero"
      ),
      selected = selected,
      width = '200px',
      multiple = F
    )
    
  })
  
  output$useroptions_enginetrends_actype <- renderUI({
    
    ns <- session$ns
    
    choices <- pool %>%
      tbl(in_schema("ecmapp", "_fleetsummary")) %>%
      filter(
        operator %in% !!input$useroptions_enginetrends_operator_pi
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
      ns("useroptions_enginetrends_actype_pi"),
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
      width = '200px',
      multiple = F
    )
    
  })
  
  output$useroptions_enginetrends_acreg <- renderUI({
    
    ns <- session$ns
    
    #req(input$useroptions_enginetrends_actype_pi, input$useroptions_enginetrends_operator_pi)
    
    choices <- list()
    
    choicesOpt <- NULL
    
    selected <- NULL
    
    if(!is.null(input$useroptions_enginetrends_actype_pi)){
      
      fleetsummary <- pool %>%
        tbl(in_schema("ecmapp", "_fleetsummary")) %>%
        filter(
          operator %in% !!input$useroptions_enginetrends_operator_pi,
          aircraft_type %in% !!input$useroptions_enginetrends_actype_pi,
          is.na(removal_datetime)
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
      
      choices <- lapply(split(df_choices$ac_reg_new, df_choices$aircraft_type), as.list)
      
      choicesOpt <- list(
        subtext = unlist(lapply(split(df_choices$subtext, df_choices$aircraft_type), as.list))
      )
      
    }
    
    pickerInput(
      ns("useroptions_enginetrends_acreg_pi"),
      label = "A/C Reg:", 
      choices = choices,
      choicesOpt = choicesOpt, 
      options = list(
        `live-search`=TRUE,
        `dropdown-align-right` = TRUE
      ),
      selected = selected,
      width = '200px',
      multiple = T
    )
    
  })
  
  output$useroptions_enginetrends_presetname <- renderUI({
    
    ns <- session$ns
    
    choices_list <- NULL
    
    choices_opt_list <- NULL
    
    selected <- NULL
    
    #req(input$enginetrends_actype_pi, input$enginetrends_operator_pi)
    if(!is.null(input$useroptions_enginetrends_operator_pi)){
      preset <- pool %>%
        tbl(in_schema("ecmapp", "preset")) %>%
        filter(
          aircraft_family %in% c(
            !!input$useroptions_enginetrends_actype_pi,
            "ALL"
          ) &
            operator %in% !!input$useroptions_enginetrends_operator_pi # OPERATOR IN SELECTED PRESET NAME !!!!!!!!!!!!!!!!!!!!!
        ) %>%
        group_by(
          report_name,
          report_family
        ) %>%
        summarise(
          count_params = n_distinct(main_param_name)
        ) %>%
        mutate(
          subtext = paste(count_params, "params")
        ) %>%
        collect()
      
      # choices_list <- list()
      # 
      # choices_opt_list <- list()
      # 
      # for(report_family in unique(preset$report_family)){
      #   
      #   choices_list[[report_family]] <- preset$report_name[preset$report_family == report_family]
      #   
      #   choices_opt_list[[report_family]] <- paste0(
      #     preset$count_params[preset$report_family == report_family],
      #     " params"
      #   )
      #   
      # }
      
      choices <- lapply(split(preset$report_name, preset$report_family), as.list)
      
      choicesOpt <- list(
        subtext = unlist(lapply(split(preset$subtext, preset$report_family), as.list))
      )
      
      userdefault_test <- pool %>% 
        tbl(in_schema("utair", "userdefault_test")) %>% 
        filter(
          user %in% !!credentials()$user
        ) %>%
        collect()
      
      if(nrow(userdefault_test) == 0){
        
        # selected <- c("TAKE OFF trends (MAIN)")
        
        selected <- NULL
        
      }
      else{
        
        selected <- jsonlite::fromJSON(userdefault_test$default)$enginetrends_presetname_pi
        
      }
      
      pickerInput(
        ns("useroptions_enginetrends_presetname_pi"),
        label = "Preset",
        choices = choices, 
        choicesOpt = choicesOpt,
        selected = selected,
        options = list(
          `live-search`=TRUE
        ),
        multiple = F
      )
    }
    
  })
  
  output$useroptions_enginetrends_plotoptions <- renderUI({
    
    ns <- session$ns
    
    userdefault_test <- pool %>% 
      tbl(in_schema("utair", "userdefault_test")) %>% 
      filter(
        user %in% !!credentials()$user
      ) %>%
      collect()
    
    if(nrow(userdefault_test) == 0){
      
      selected <- NULL
      
    }
    else{
      
      selected <- jsonlite::fromJSON(userdefault_test$default)
      
    }
    
    #fluidRow(
    column(
      12,
      wellPanel(
      radioButtons(
        ns("rb_engine_position"), 
        label = NULL,
        choices = list(
          "All" = 1,
          "Engine pos. 1" = 2,
          "Engine pos. 2" = 3
        ), 
        #selected = 1
        selected = as.numeric(selected$rb_engine_position)
      )),
      
      
      radioButtons(
        ns("rb_enable_smooth"), 
        label = NULL,
        choices = list(
          "Only smooth" = 1,
          "Only raw" = 2,
          "Smooth and raw" = 3
        ), 
        #selected = 3
        selected = as.numeric(selected$rb_enable_smooth)
      ),
      
      numericInput(
        ns("smooth_window"),
        label = NULL,
        as.numeric(selected$smooth_window), 
        min = 1, 
        max = 100
      ),
      
      checkboxGroupInput(
        ns("cgi_show_alerts"),
        label = NULL,
        choices = c(
          "Show alerts",
          "Show maintenance actions",
          "Show previous installations"
        ),
        # selected = c(
        #   "Show alerts",
        #   "Show previous installations"
        # ),
        selected = selected$cgi_show_alerts,
        inline = FALSE
      ),
      
      radioGroupButtons(
        ns("rb_graph_size"),
        label = NULL,
        size = "sm",
        status = "warning",
        choices = c(
          `<i class='fa fa-th-large'></i>` = "multiple", 
          `<i class='fa fa-th-list'></i>` = "line", 
          `<i class='fa fa-stop'></i>` = "one"
        ),
        #selected = "one",
        selected = selected$rb_graph_size,
        justified = FALSE
      ),
      
      radioButtons(
        ns("rb_range_selector"), 
        label = NULL,
        choices = list(
          "1m",
          "3m",
          "6m",
          "1y",
          "YTD",
          "ALL"
        ), 
        #selected = "ALL"
        selected = selected$rb_range_selector
      )
    )
    #)
    
  })
  
  output$fleetreport_operator <- renderUI({
    
    # ns <- session$ns
    # # browser()
    # 
    # pickerInput(
    #   ns("fleetreports_operator_pi"),
    #   label = "Operator",
    #   choices = "utair", 
    #   options = list(
    #     `live-search`=TRUE,
    #     `actions-box` = TRUE,
    #     `deselect-all-text` = "deselect",
    #     `select-all-text` = "select all",
    #     `none-selected-text` = "zero"
    #   ),
    #   selected = "utair",
    #   width = '200px',
    #   multiple = F
    # )
    
    ns <- session$ns
    
    fleetsummary <- pool %>% 
      tbl(in_schema("ecmapp", "_fleetsummary")) %>% 
      collect()
    
    userdefault_test <- pool %>% 
      tbl(in_schema("utair", "userdefault_test")) %>% 
      filter(
        user %in% !!credentials()$user
      ) %>%
      collect()
    
    if(nrow(userdefault_test) == 0){
      
      # selected <- unique(fleetsummary$operator)
      
      selected <- NULL
      
    }
    else{
      
      selected <- jsonlite::fromJSON(userdefault_test$default)$fleetreports_operator_pi
      
    }
    
    pickerInput(
      ns("fleetreports_operator_pi"),
      label = "Operator",
      choices = unique(fleetsummary$operator), 
      options = list(
        `live-search`=TRUE,
        `actions-box` = TRUE,
        `deselect-all-text` = "deselect",
        `select-all-text` = "select all",
        `none-selected-text` = "zero"
      ),
      selected = selected,
      width = '200px',
      multiple = F
    )
    
  })
  
  output$fleetreport_actype <- renderUI({
    
    ns <- session$ns
    
    choices <- pool %>%
      tbl(in_schema("ecmapp", "_fleetsummary")) %>%
      filter(
        operator %in% !!input$fleetreports_operator_pi
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
      
      selected <- jsonlite::fromJSON(userdefault_test$default)$fleetreports_actype_pi
      
    }
    
    pickerInput(
      ns("fleetreports_actype_pi"),
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
      selected = selected,#"ATR72-212",
      multiple = T
    )
    
  })
  
  output$fleetreport_acreg <- renderUI({
    
    ns <- session$ns
    
    #req(input$fleetreports_actype_pi, input$fleetreports_operator_pi)
    
    choices <- list()
    
    choicesOpt <- NULL
    
    selected <- NULL
    
    if(!is.null(input$fleetreports_actype_pi)){
      
      fleetsummary <- pool %>%
        tbl(in_schema("ecmapp", "_fleetsummary")) %>%
        filter(
          operator %in% !!input$fleetreports_operator_pi,
          aircraft_type %in% !!input$fleetreports_actype_pi,
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
        
        selected <- jsonlite::fromJSON(userdefault_test$default)$fleetreports_acreg_pi
        
      }
    }
    pickerInput(
      ns("fleetreports_acreg_pi"),
      label = "A/C Reg:", 
      choices = choices,
      choicesOpt = choicesOpt, 
      options = list(
        `live-search`=TRUE,
        `actions-box` = TRUE,
        `deselect-all-text` = "deselect",
        `select-all-text` = "select all",
        `none-selected-text` = "zero"
      ),
      selected = selected,
      multiple = T
    )
    
  })
  
  output$fleetreport_presetname <- renderUI({
    
    ns <- session$ns
    
    choices_list <- NULL
    
    choices_opt_list <- NULL
    
    selected <- NULL
    
    #req(input$enginetrends_actype_pi, input$enginetrends_operator_pi)
    if(!is.null(input$fleetreports_operator_pi)){
      preset <- pool %>%
        tbl(in_schema("ecmapp", "preset")) %>%
        filter(
          aircraft_family %in% c(
            !!input$fleetreports_actype_pi,
            "ALL"
          ) &
            operator %in% !!input$fleetreports_operator_pi # OPERATOR IN SELECTED PRESET NAME !!!!!!!!!!!!!!!!!!!!!
        ) %>%
        group_by(
          report_name,
          report_family
        ) %>%
        summarise(
          count_params = n_distinct(main_param_name)
        ) %>%
        mutate(
          subtext = paste(count_params, "params")
        ) %>%
        collect()
      
      # choices_list <- list()
      # 
      # choices_opt_list <- list()
      # 
      # for(report_family in unique(preset$report_family)){
      #   
      #   choices_list[[report_family]] <- preset$report_name[preset$report_family == report_family]
      #   
      #   choices_opt_list[[report_family]] <- paste0(
      #     preset$count_params[preset$report_family == report_family],
      #     " params"
      #   )
      #   
      # }
      
      choices <- lapply(split(preset$report_name, preset$report_family), as.list)
      
      choicesOpt <- list(
        subtext = unlist(lapply(split(preset$subtext, preset$report_family), as.list))
      )
      
      userdefault_test <- pool %>% 
        tbl(in_schema("utair", "userdefault_test")) %>% 
        filter(
          user %in% !!credentials()$user
        ) %>%
        collect()
      
      if(nrow(userdefault_test) == 0){
        
        # selected <- c("TAKE OFF trends (MAIN)")
        
        selected <- NULL
        
      }
      else{
        
        selected <- jsonlite::fromJSON(userdefault_test$default)$fleetreports_presetname_pi
        
      }
      
      pickerInput(
        ns("fleetreports_presetname_pi"),
        label = "Preset",
        choices = choices, 
        choicesOpt = choicesOpt,
        selected = selected,
        options = list(
          `live-search`=TRUE
        ),
        multiple = F
      )
    }
    
  })
  
  observeEvent(input$ab_save_useroptions,{
    showModal(modal_save_useroptions)
  })
  
  modal_save_useroptions <- modalDialog(
    fluidPage(
      h3(
        paste0(
          "Do you really want to save default user options"
        )
      ),
      # use_waiter(),
      actionBttn(ns("modal_ab_modal_save_useroptions"), "Save user options")
    ),
    size="l"
  )
  
  observeEvent(input$modal_ab_modal_save_useroptions,{
    
    userdefault_test <- pool %>%
      tbl(in_schema("utair", "userdefault_test")) %>%
      collect()
    # browser()
    if(nrow(userdefault_test[userdefault_test$user == credentials()$user,]) == 0){
      
      userdefault_test_new <- data.frame(user = credentials()$user)
      
      userdefault_test_new$default <- jsonlite::toJSON(
        list(
          enginetrends_operator_pi = input$useroptions_enginetrends_operator_pi,
          enginetrends_actype_pi = input$useroptions_enginetrends_actype_pi,
          enginetrends_acreg_pi = input$useroptions_enginetrends_acreg_pi ,
          enginetrends_presetname_pi = input$useroptions_enginetrends_presetname_pi,
          rb_engine_position = input$rb_engine_position,
          rb_enable_smooth = input$rb_enable_smooth,
          smooth_window = input$smooth_window,
          cgi_show_alerts = input$cgi_show_alerts,
          rb_graph_size = input$rb_graph_size,
          rb_range_selector = input$rb_range_selector,
          
          fleetreports_operator_pi = input$fleetreports_operator_pi,
          fleetreports_actype_pi = input$fleetreports_actype_pi,
          fleetreports_acreg_pi = input$fleetreports_acreg_pi,
          fleetreports_presetname_pi = input$fleetreports_presetname_pi
        ),
        auto_unbox = TRUE
      )
      
      userdefault_test <- rbind(
        userdefault_test,
        userdefault_test_new
      )
      
    }
    else{
      
      userdefault_test$default[
        userdefault_test$user == credentials()$user
      ] <- jsonlite::toJSON(
        list(
          enginetrends_operator_pi = input$useroptions_enginetrends_operator_pi,
          enginetrends_actype_pi = input$useroptions_enginetrends_actype_pi,
          enginetrends_acreg_pi = input$useroptions_enginetrends_acreg_pi ,
          enginetrends_presetname_pi = input$useroptions_enginetrends_presetname_pi,
          rb_engine_position = input$rb_engine_position,
          rb_enable_smooth = input$rb_enable_smooth,
          smooth_window = input$smooth_window,
          cgi_show_alerts = input$cgi_show_alerts,
          rb_graph_size = input$rb_graph_size,
          rb_range_selector = input$rb_range_selector,
          
          fleetreports_operator_pi = input$fleetreports_operator_pi,
          fleetreports_actype_pi = input$fleetreports_actype_pi,
          fleetreports_acreg_pi = input$fleetreports_acreg_pi,
          fleetreports_presetname_pi = input$fleetreports_presetname_pi
        ),
        auto_unbox = TRUE
      )
      
    }
    
    dbWriteTable(
      pool, 
      c("utair", "userdefault_test"), 
      value = userdefault_test, 
      row.names = FALSE, 
      overwrite = TRUE
    )
    
    removeModal()
    
    showNotification(
      paste0(
        "Default settings have been saved"
      )
    )
    
    # w$hide()
    
  })
  
  
  
  output$useroptions_workspace <- renderUI({
    
    fluidRow(
      
      bs4Card(
        width = 12,
        headerBorder = FALSE,
        collapsible = FALSE,
          fluidRow(
            actionBttn(ns("ab_save_useroptions"), "Save default")
          )
      ),
      
      bs4TabCard(
        width = 6,
        height = '900px',
        maximizable = TRUE,
        solidHeader = FALSE,
        sidebar = boxSidebar(),
        tabPanel(
          title = "Engine Trends",
          fluidRow(
            column(
              3,
              uiOutput(ns("useroptions_enginetrends_operator"))
            ),
            hr(),
            column(
              3,
              uiOutput(ns("useroptions_enginetrends_actype"))
            ),
            hr(),
            column(
              3,
              uiOutput(ns("useroptions_enginetrends_acreg"))
            ),
            hr(),
            column(
              3,
              uiOutput(ns("useroptions_enginetrends_presetname"))
            ),
            hr(),
            uiOutput(ns("useroptions_enginetrends_plotoptions")),
            hr()
          )
        )
      ),
      bs4TabCard(
        width = 6,
        height = '900px',
        maximizable = TRUE,
        solidHeader = FALSE,
        sidebar = boxSidebar(),
        tabPanel(
          title = "Fleet Reports",
          # uiOutput(ns("fleetreport_operator")),
          # hr(),
          # uiOutput(ns("fleetreport_actype")),
          # hr(),
          # uiOutput(ns("fleetreport_acreg")),
          # hr(),
          # uiOutput(ns("fleetreport_presetname"))
          
          fluidRow(
            column(
              3,
              uiOutput(ns("fleetreport_operator"))
            ),
            hr(),
            column(
              3,
              uiOutput(ns("fleetreport_actype"))
            ),
            hr(),
            column(
              3,
              uiOutput(ns("fleetreport_acreg"))
            ),
            hr(),
            column(
              3,
              uiOutput(ns("fleetreport_presetname"))
            ),
            hr()
          )
        )
      )
    )
    
    
  })
  
}